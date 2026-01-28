from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from src.models.database import DatabaseService, UserToken
from src.utils.logger import get_logger, console
from datetime import datetime
from typing import Optional
import json
import os

logger = get_logger("google_auth")


class GoogleAuthService:
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    CLIENT_SECRET_FILE = 'client_secret.json'
    
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        
        current_dir = os.getcwd()
        full_path = os.path.join(current_dir, self.CLIENT_SECRET_FILE)
        
        logger.info(f"Looking for {self.CLIENT_SECRET_FILE} in: {current_dir}")
        console.print(f"[debug]🔍 Looking for {self.CLIENT_SECRET_FILE}[/debug]")
        console.print(f"[debug]📁 Path: {current_dir}[/debug]")
        console.print(f"[debug]{'✅' if os.path.exists(full_path) else '❌'} File exists: {os.path.exists(full_path)}[/debug]")
        
        if not os.path.exists(self.CLIENT_SECRET_FILE):
            logger.error(f"Client secret file not found: {self.CLIENT_SECRET_FILE}")
            console.print(f"[error]❌ Client secret file not found: {self.CLIENT_SECRET_FILE}[/error]")
            console.print(f"[error]📂 Current directory: {current_dir}[/error]")
            raise FileNotFoundError(f"Please place {self.CLIENT_SECRET_FILE} in the project root: {current_dir}")
    
    def generate_auth_url(self, telegram_user_id: int) -> str:
        flow = InstalledAppFlow.from_client_secrets_file(
            self.CLIENT_SECRET_FILE,
            scopes=self.SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent'
        )
        
        logger.info(f"Generated auth URL for Telegram user {telegram_user_id}")
        console.print(f"[success]🔗 Auth URL generated for user {telegram_user_id}[/success]")
        
        return auth_url
    
    def exchange_code_for_tokens(self, telegram_user_id: int, auth_code: str) -> bool:
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.CLIENT_SECRET_FILE,
                scopes=self.SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            
            self._save_token(telegram_user_id, credentials)
            
            logger.info(f"Successfully exchanged code for tokens for Telegram user {telegram_user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to exchange code for Telegram user {telegram_user_id}: {e}", exc_info=True)
            return False
    
    def _save_token(self, telegram_user_id: int, credentials: Credentials):
        with self.db_service.get_session() as session:
            existing = session.query(UserToken).filter(
                UserToken.user_id == telegram_user_id
            ).first()
            
            if existing:
                existing.access_token = credentials.token
                existing.refresh_token = credentials.refresh_token or existing.refresh_token
                existing.token_uri = credentials.token_uri
                existing.client_id = credentials.client_id
                existing.client_secret = credentials.client_secret
                existing.scopes = json.dumps(list(credentials.scopes))
                existing.expiry = credentials.expiry
                existing.updated_at = datetime.utcnow()
                
                logger.info(f"Updated tokens for Telegram user {telegram_user_id}")
            else:
                new_token = UserToken(
                    user_id=telegram_user_id,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    token_uri=credentials.token_uri,
                    client_id=credentials.client_id,
                    client_secret=credentials.client_secret,
                    scopes=json.dumps(list(credentials.scopes)),
                    expiry=credentials.expiry
                )
                session.add(new_token)
                
                logger.info(f"Saved new tokens for Telegram user {telegram_user_id}")
            
            session.commit()
    
    def get_credentials(self, telegram_user_id: int) -> Optional[Credentials]:
        with self.db_service.get_session() as session:
            token_row = session.query(UserToken).filter(
                UserToken.user_id == telegram_user_id
            ).first()
            
            if not token_row:
                logger.info(f"No tokens found for Telegram user {telegram_user_id}")
                return None
            
            credentials = Credentials(
                token=token_row.access_token,
                refresh_token=token_row.refresh_token,
                token_uri=token_row.token_uri,
                client_id=token_row.client_id,
                client_secret=token_row.client_secret,
                scopes=json.loads(token_row.scopes)
            )
            
            if token_row.expiry:
                credentials.expiry = token_row.expiry
            
            if credentials.expired and credentials.refresh_token:
                logger.info(f"Token expired for Telegram user {telegram_user_id}, refreshing...")
                try:
                    credentials.refresh(Request())
                    self._save_token(telegram_user_id, credentials)
                    logger.info(f"Successfully refreshed token for Telegram user {telegram_user_id}")
                except Exception as e:
                    logger.error(f"Failed to refresh token for Telegram user {telegram_user_id}: {e}", exc_info=True)
                    return None
            
            return credentials
    
    def has_valid_credentials(self, telegram_user_id: int) -> bool:
        credentials = self.get_credentials(telegram_user_id)
        return credentials is not None and credentials.valid
    
    def revoke_credentials(self, telegram_user_id: int) -> bool:
        try:
            with self.db_service.get_session() as session:
                deleted = session.query(UserToken).filter(
                    UserToken.user_id == telegram_user_id
                ).delete()
                session.commit()
                
                if deleted > 0:
                    logger.info(f"Revoked credentials for Telegram user {telegram_user_id}")
                    return True
                else:
                    logger.warning(f"No credentials to revoke for Telegram user {telegram_user_id}")
                    return False
        
        except Exception as e:
            logger.error(f"Failed to revoke credentials for Telegram user {telegram_user_id}: {e}", exc_info=True)
            return False
