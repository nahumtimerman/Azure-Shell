import base64
import os

from cloudshell.core.cryptography.aes_service import AESCipher
from cloudshell.core.cryptography.rsa_service import RsaService


class CryptographyDto(object):
    def __init__(self):
        """
        """
        self.encrypted_input = ""
        self.encrypted_asymmetric_key = ""


class CryptographyService(object):
    def __init__(self):
        """
        """

    def encrypt(self, input):
        secret_key = base64.b64encode(os.urandom(16))

        encrypted_input = AESCipher(secret_key).encrypt(input)
        encrypted_secret_key = RsaService.encrypt(secret_key)

        cryptography_dto = CryptographyDto()
        cryptography_dto.encrypted_input = encrypted_input
        cryptography_dto.encrypted_asymmetric_key = encrypted_secret_key

        return cryptography_dto
