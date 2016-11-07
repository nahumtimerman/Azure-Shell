import jsonpickle

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient

from cloudshell.core.context.error_handling_context import ErrorHandlingContext
from cloudshell.shell.core.session.cloudshell_session import CloudShellSessionContext
from cloudshell.cp.azure.common.deploy_data_holder import DeployDataHolder
from cloudshell.cp.azure.domain.context.validators_factory_context import ValidatorsFactoryContext
from cloudshell.cp.azure.domain.services.tags import TagService
from cloudshell.cp.azure.domain.vm_management.operations.delete_operation import DeleteAzureVMOperation
from cloudshell.shell.core.session.logging_session import LoggingSessionContext
from cloudshell.cp.azure.domain.context.azure_client_context import AzureClientFactoryContext
from cloudshell.cp.azure.domain.services.network_service import NetworkService
from cloudshell.cp.azure.domain.services.parsers.azure_model_parser import AzureModelsParser
from cloudshell.cp.azure.domain.services.parsers.command_result_parser import CommandResultsParser
from cloudshell.cp.azure.domain.services.virtual_machine_service import VirtualMachineService
from cloudshell.cp.azure.domain.services.storage_service import StorageService
from cloudshell.cp.azure.domain.services.vm_credentials_service import VMCredentialsService
from cloudshell.cp.azure.domain.services.key_pair import KeyPairService
from cloudshell.cp.azure.domain.services.security_group import SecurityGroupService
from cloudshell.cp.azure.domain.vm_management.operations.deploy_operation import DeployAzureVMOperation
from cloudshell.cp.azure.domain.vm_management.operations.power_operation import PowerAzureVMOperation
from cloudshell.cp.azure.domain.vm_management.operations.refresh_ip_operation import RefreshIPOperation
from cloudshell.cp.azure.domain.vm_management.operations.prepare_connectivity_operation import \
    PrepareConnectivityOperation


class AzureShell(object):
    def __init__(self):
        self.command_result_parser = CommandResultsParser()
        self.model_parser = AzureModelsParser()
        self.vm_service = VirtualMachineService()
        self.network_service = NetworkService()
        self.storage_service = StorageService()
        self.tags_service = TagService()
        self.vm_credentials_service = VMCredentialsService()
        self.key_pair_service = KeyPairService(storage_service=self.storage_service)
        self.security_group_service = SecurityGroupService()

        self.prepare_connectivity_operation = PrepareConnectivityOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            storage_service=self.storage_service,
            tags_service=self.tags_service,
            key_pair_service=self.key_pair_service,
            security_group_service=self.security_group_service)

        self.deploy_azure_vm_operation = DeployAzureVMOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            storage_service=self.storage_service,
            key_pair_service=self.key_pair_service,
            tags_service=self.tags_service,
            vm_credentials_service=self.vm_credentials_service,
            security_group_service=self.security_group_service)

        self.power_vm_operation = PowerAzureVMOperation(vm_service=self.vm_service)

        self.refresh_ip_operation = RefreshIPOperation(vm_service=self.vm_service)

        self.delete_azure_vm_operation = DeleteAzureVMOperation(
            vm_service=self.vm_service,
            network_service=self.network_service,
            tags_service=self.tags_service)

    def deploy_azure_vm(self, command_context, deployment_request):
        """Will deploy Azure Image on the cloud provider

        :param ResourceCommandContext command_context:
        :param JSON Obj deployment_request:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)
                azure_vm_deployment_model = self.model_parser.convert_to_deployment_resource_model(deployment_request)

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    with ValidatorsFactoryContext() as validator_factory:
                        logger.info('Deploying Azure VM')
                        compute_client = azure_clients_factory.get_client(ComputeManagementClient)
                        network_client = azure_clients_factory.get_client(NetworkManagementClient)
                        storage_client = azure_clients_factory.get_client(StorageManagementClient)
                        reservation = self.model_parser.convert_to_reservation_model(command_context.reservation)

                        if azure_vm_deployment_model.password:
                            with CloudShellSessionContext(command_context) as cloudshell_session:
                                decrypted_pass = cloudshell_session.DecryptPassword(azure_vm_deployment_model.password)
                                azure_vm_deployment_model.password = decrypted_pass.Value

                        deploy_data = self.deploy_azure_vm_operation.deploy(
                            azure_vm_deployment_model=azure_vm_deployment_model,
                            cloud_provider_model=cloud_provider_model,
                            reservation=reservation,
                            network_client=network_client,
                            compute_client=compute_client,
                            storage_client=storage_client,
                            validator_factory=validator_factory)

                        return self.command_result_parser.set_command_result(deploy_data)

    def prepare_connectivity(self, context, request):
        """

        :param context:
        :param request:
        :return:
        """
        with LoggingSessionContext(context) as logger:
            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(context.resource)

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    logger.info('Preparing Connectivity for Azure VM')
                    resource_client = azure_clients_factory.get_client(ResourceManagementClient)
                    network_client = azure_clients_factory.get_client(NetworkManagementClient)
                    storage_client = azure_clients_factory.get_client(StorageManagementClient)

                    prepare_connectivity_request = DeployDataHolder(jsonpickle.decode(request))
                    prepare_connectivity_request = getattr(prepare_connectivity_request, 'driverRequest', None)

                    result = self.prepare_connectivity_operation.prepare_connectivity(
                        reservation=self.model_parser.convert_to_reservation_model(context.reservation),
                        cloud_provider_model=cloud_provider_model,
                        storage_client=storage_client,
                        resource_client=resource_client,
                        network_client=network_client,
                        logger=logger,
                        request=prepare_connectivity_request)

                    return self.command_result_parser.set_command_result({'driverResponse': {'actionResults': result}})

    def cleanup_connectivity(self, command_context):
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    logger.info('Teardown...')

                    resource_client = azure_clients_factory.get_client(ResourceManagementClient)
                    network_client = azure_clients_factory.get_client(NetworkManagementClient)

                    resource_group_name = command_context.reservation.reservation_id

                    self.delete_azure_vm_operation.delete_resource_group(
                        resource_client=resource_client,
                        group_name=resource_group_name
                    )

                    self.delete_azure_vm_operation.delete_sandbox_subnet(
                        network_client=network_client,
                        cloud_provider_model=cloud_provider_model,
                        resource_group_name=resource_group_name
                    )

    def delete_azure_vm(self, command_context):
        with LoggingSessionContext(command_context) as logger:

            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(
                    command_context.remote_endpoints[0])
                resource_group_name = next(o.value for o in
                                           data_holder.vmdetails.vmCustomParams if o.name == 'resource_group')

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    logger.info('Deleting Azure VM')

                    compute_client = azure_clients_factory.get_client(ComputeManagementClient)
                    network_client = azure_clients_factory.get_client(NetworkManagementClient)
                    vm_name = command_context.remote_endpoints[0].fullname

                    self.delete_azure_vm_operation.delete(
                        compute_client=compute_client,
                        network_client=network_client,
                        group_name=resource_group_name,
                        vm_name=vm_name,
                        logger=logger)

    def power_on_vm(self, command_context):
        """Power on Azure VM

        :param ResourceCommandContext command_context:
        :return:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)
                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                group_name = reservation.reservation_id

                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    logger.info('Starting power on operation on Azure VM {}'.format(vm_name))

                    compute_client = azure_clients_factory.get_client(ComputeManagementClient)

                    self.power_vm_operation.power_on(compute_client=compute_client,
                                                     resource_group_name=group_name,
                                                     vm_name=vm_name)

                    logger.info('Azure VM {} was successfully powered on'.format(vm_name))

                    with CloudShellSessionContext(command_context) as cloudshell_session:
                        cloudshell_session.SetResourceLiveStatus(resource.fullname, "Online", "Active")

    def power_off_vm(self, command_context):
        """Power off Azure VM

        :param ResourceCommandContext command_context:
        :return:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)
                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                group_name = reservation.reservation_id

                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name

                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    logger.info('Starting power off operation on Azure VM {}'.format(vm_name))

                    compute_client = azure_clients_factory.get_client(ComputeManagementClient)

                    self.power_vm_operation.power_off(compute_client=compute_client,
                                                      resource_group_name=group_name,
                                                      vm_name=vm_name)

                    logger.info('Azure VM {} was successfully powered off'.format(vm_name))

                    with CloudShellSessionContext(command_context) as cloudshell_session:
                        cloudshell_session.SetResourceLiveStatus(resource.fullname, "Offline", "Powered Off")

    def refresh_ip(self, command_context):
        """Refresh private and public IPs on the Cloudshell resource

        :param ResourceRemoteCommandContext command_context:
        """
        with LoggingSessionContext(command_context) as logger:
            with ErrorHandlingContext(logger):
                logger.info("Starting Refresh IP operation")
                cloud_provider_model = self.model_parser.convert_to_cloud_provider_resource_model(
                    command_context.resource)
                reservation = self.model_parser.convert_to_reservation_model(command_context.remote_reservation)
                resource = command_context.remote_endpoints[0]
                data_holder = self.model_parser.convert_app_resource_to_deployed_app(resource)
                vm_name = data_holder.name
                group_name = reservation.reservation_id
                private_ip = self.model_parser.get_private_ip_from_connected_resource_details(command_context)
                public_ip = self.model_parser.get_public_ip_from_connected_resource_details(command_context)
                resource_fullname = self.model_parser.get_connected_resource_fullname(command_context)
                with AzureClientFactoryContext(cloud_provider_model) as azure_clients_factory:
                    compute_client = azure_clients_factory.get_client(ComputeManagementClient)
                    network_client = azure_clients_factory.get_client(NetworkManagementClient)
                    with CloudShellSessionContext(command_context) as cloudshell_session:
                        self.refresh_ip_operation.refresh_ip(cloudshell_session=cloudshell_session,
                                                             compute_client=compute_client,
                                                             network_client=network_client,
                                                             resource_group_name=group_name,
                                                             vm_name=vm_name,
                                                             private_ip_on_resource=private_ip,
                                                             public_ip_on_resource=public_ip,
                                                             resource_fullname=resource_fullname)

                    logger.info('Azure VM IPs were successfully refreshed'.format(vm_name))
