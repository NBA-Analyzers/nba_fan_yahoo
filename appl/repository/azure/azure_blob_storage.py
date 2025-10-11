import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
import logging
from dotenv import load_dotenv

load_dotenv(".env") # Loads from .env or .env.vault if DOTENV_KEY is set

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AzureBlobStorage:
    """
    Handles Azure Blob Storage operations for fantasy league data.
    Responsible for uploading and fetching data from Azure Blob Storage.
    """
    
    def __init__(self, connection_string: Optional[str] = None, container_name: str = "fantasy-league-data"):
        """
        Initialize Azure Blob Storage client.
        
        Args:
            connection_string (str): Azure Storage connection string. 
                                   If None, will try to get from environment variable AZURE_STORAGE_CONNECTION_STRING
            container_name (str): Name of the blob container to use
        """
        self.connection_string = connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not self.connection_string:
            raise ValueError("Azure Storage connection string is required. Set AZURE_STORAGE_CONNECTION_STRING environment variable or pass it to constructor.")
        
        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self.container_client = self.blob_service_client.get_container_client(container_name)
        
        # Ensure container exists
        self._ensure_container_exists()
    
    def _ensure_container_exists(self):
        """Ensure the blob container exists, create if it doesn't."""
        try:
            self.container_client.get_container_properties()
            logger.info(f"Container '{self.container_name}' already exists")
        except ResourceNotFoundError:
            logger.info(f"Creating container '{self.container_name}'")
            self.container_client.create_container()
    
    def upload_json_data(self, data: Dict[str, Any], blob_name: str, overwrite: bool = True) -> bool:
        """
        Upload JSON data to Azure Blob Storage.
        
        Args:
            data (Dict[str, Any]): Data to upload as JSON
            blob_name (str): Name of the blob in the container
            overwrite (bool): Whether to overwrite existing blob
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Convert data to JSON string
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            
            # Upload the data
            blob_client.upload_blob(json_data, overwrite=overwrite)
            
            logger.info(f"Successfully uploaded data to blob: {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error uploading data to blob '{blob_name}': {str(e)}")
            return False
    
    def upload_file(self, file_path: str, blob_name: Optional[str] = None, overwrite: bool = True) -> bool:
        """
        Upload a local file to Azure Blob Storage.
        
        Args:
            file_path (str): Path to the local file
            blob_name (str): Name of the blob in the container. If None, uses the filename
            overwrite (bool): Whether to overwrite existing blob
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return False
            
            if blob_name is None:
                blob_name = os.path.basename(file_path)
            
            blob_client = self.container_client.get_blob_client(blob_name)
            
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=overwrite)
            
            logger.info(f"Successfully uploaded file '{file_path}' to blob: {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error uploading file '{file_path}' to blob '{blob_name}': {str(e)}")
            return False
    
    def download_json_data(self, blob_name: str) -> Optional[Dict[str, Any]]:
        """
        Download JSON data from Azure Blob Storage.
        
        Args:
            blob_name (str): Name of the blob in the container
            
        Returns:
            Optional[Dict[str, Any]]: Downloaded data as dictionary, None if failed
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Download the blob content
            blob_data = blob_client.download_blob()
            content = blob_data.readall().decode('utf-8')
            
            # Parse JSON
            data = json.loads(content)
            
            logger.info(f"Successfully downloaded data from blob: {blob_name}")
            return data
            
        except ResourceNotFoundError:
            logger.warning(f"Blob not found: {blob_name}")
            return None
        except Exception as e:
            logger.error(f"Error downloading data from blob '{blob_name}': {str(e)}")
            return None
    
    def download_file(self, blob_name: str, local_file_path: str) -> bool:
        """
        Download a file from Azure Blob Storage to local storage.
        Creates the file in the current directory and downloads to that path.
        
        Args:
            blob_name (str): Name of the blob in the container
            local_file_path (str): Local path where to save the file (relative to current directory)
            
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            
            # Create the file in the current directory
            with open(local_file_path, "wb") as file:
                blob_data = blob_client.download_blob()
                file.write(blob_data.readall())
            
            logger.info(f"Successfully downloaded blob '{blob_name}' to '{local_file_path}' in current directory")
            return True
            
        except ResourceNotFoundError:
            logger.warning(f"Blob not found: {blob_name}")
            return False
        except Exception as e:
            logger.error(f"Error downloading blob '{blob_name}' to '{local_file_path}': {str(e)}")
            return False
    
    def list_blobs(self, name_starts_with: Optional[str] = None) -> List[str]:
        """
        List all blobs in the container.
        
        Args:
            name_starts_with (str): Filter blobs that start with this prefix
            
        Returns:
            List[str]: List of blob names
        """
        try:
            blobs = self.container_client.list_blobs(name_starts_with=name_starts_with)
            blob_names = [blob.name for blob in blobs]
            
            logger.info(f"Found {len(blob_names)} blobs in container '{self.container_name}'")
            return blob_names
            
        except Exception as e:
            logger.error(f"Error listing blobs: {str(e)}")
            return []
    
    def delete_blob(self, blob_name: str) -> bool:
        """
        Delete a blob from the container.
        
        Args:
            blob_name (str): Name of the blob to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.delete_blob()
            
            logger.info(f"Successfully deleted blob: {blob_name}")
            return True
            
        except ResourceNotFoundError:
            logger.warning(f"Blob not found for deletion: {blob_name}")
            return False
        except Exception as e:
            logger.error(f"Error deleting blob '{blob_name}': {str(e)}")
            return False
    
    def blob_exists(self, blob_name: str) -> bool:
        """
        Check if a blob exists in the container.
        
        Args:
            blob_name (str): Name of the blob to check
            
        Returns:
            bool: True if blob exists, False otherwise
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error checking if blob '{blob_name}' exists: {str(e)}")
            return False
    
    def get_blob_url(self, blob_name: str) -> Optional[str]:
        """
        Get the URL for a blob.
        
        Args:
            blob_name (str): Name of the blob
            
        Returns:
            Optional[str]: URL of the blob, None if blob doesn't exist
        """
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            return blob_client.url
        except Exception as e:
            logger.error(f"Error getting URL for blob '{blob_name}': {str(e)}")
            return None
    
    def upload_league_data(self, league_id: str, data_type: str, data: Dict[str, Any], timestamp: Optional[str] = None) -> bool:
        """
        Upload league data with organized naming convention.
        
        Args:
            league_id (str): League identifier
            data_type (str): Type of data (e.g., 'standings', 'matchups', 'roster')
            data (Dict[str, Any]): Data to upload
            timestamp (str): Optional timestamp for versioning. If None, uses current time
            
        Returns:
            bool: True if upload successful, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        blob_name = f"{league_id}/{data_type}/{timestamp}.json"
        return self.upload_json_data(data, blob_name)
    
    def download_latest_league_data(self, league_id: str, data_type: str) -> Optional[Dict[str, Any]]:
        """
        Download the latest version of league data.
        
        Args:
            league_id (str): League identifier
            data_type (str): Type of data to download
            
        Returns:
            Optional[Dict[str, Any]]: Latest data, None if not found
        """
        # List all blobs for this league and data type
        prefix = f"{league_id}/{data_type}/"
        blobs = self.list_blobs(name_starts_with=prefix)
        
        if not blobs:
            logger.warning(f"No data found for league '{league_id}' and type '{data_type}'")
            return None
        
        # Get the most recent blob (highest timestamp)
        latest_blob = sorted(blobs)[-1]
        return self.download_json_data(latest_blob) 