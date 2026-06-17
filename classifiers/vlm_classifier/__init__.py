from models.vlm_client import VLMClient
from schemas.documents import ClassificationResult
from core.exceptions import DocumentUnknownError

class VLMClassifier:
    """
    A document classifier powered by a Vision-Language Model.
    """
    
    def __init__(self, vlm_client: VLMClient):
        self.vlm_client = vlm_client

    async def classify_document(self, image_b64: str) -> ClassificationResult:
        """
        Classifies a document image and returns a ClassificationResult.
        
        Args:
            image_b64: The base64-encoded image data.
            
        Returns:
            ClassificationResult: The parsed document type and confidence.
            
        Raises:
            DocumentUnknownError: If the document is classified as 'unknown' or if the confidence is below 0.6.
            VLMClientError: If the VLM client fails or returns unparseable output.
        """
        result_dict = await self.vlm_client.classify(image_b64)
        
        # Pydantic validates the structure, types, and constraints (e.g. 0.0 <= confidence <= 1.0)
        result = ClassificationResult(**result_dict)
        
        if result.confidence < 0.6 or result.document_type == "unknown":
            raise DocumentUnknownError(
                f"Document could not be reliably classified (type: {result.document_type}, confidence: {result.confidence})"
            )
            
        return result
