import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

class EncryptionService:
    """Service for encrypting and decrypting sensitive data"""
    
    @staticmethod
    def _get_key():
        """Generate a key from the application secret key"""
        # Use a fixed salt for deterministic key generation
        salt = b'fixed_salt_for_db_passwords'
        
        # Use the app's secret key as the password
        password = settings.SECRET_KEY.encode()
        
        # Generate a key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    @classmethod
    def encrypt(cls, text: str) -> str:
        """Encrypt a string"""
        if not text:
            return text
            
        key = cls._get_key()
        f = Fernet(key)
        encrypted_data = f.encrypt(text.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    
    @classmethod
    def decrypt(cls, encrypted_text: str) -> str:
        """Decrypt a string"""
        if not encrypted_text:
            return encrypted_text
            
        try:
            key = cls._get_key()
            f = Fernet(key)
            decrypted_data = f.decrypt(base64.urlsafe_b64decode(encrypted_text))
            return decrypted_data.decode()
        except Exception as e:
            # If decryption fails, it might be an unencrypted password (legacy data)
            # In that case, return the original text
            return encrypted_text
