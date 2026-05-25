import logging
from typing import Tuple

import torch
from PIL import Image
from torchvision import transforms
from transformers import AutoModelForImageClassification

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def load_vit_model(
    model_name: str = "yuh0512/vit_skin_cancer_hf_v2",
    device: torch.device | None = None,
) -> Tuple[AutoModelForImageClassification, torch.device]:
    """Load a fine-tuned ViT model from Hugging Face with label mapping."""
    lesion_type_dict = {
        "akiec": "Actinic keratoses",
        "bcc": "Basal cell carcinoma",
        "bkl": "Benign keratosis-like lesions",
        "df": "Dermatofibroma",
        "mel": "Melanoma",
        "nv": "Melanocytic nevi",
        "vasc": "Vascular lesions",
    }
    label_order = ["bkl", "bcc", "akiec", "vasc", "nv", "mel", "df"]
    id2label = {i: lesion_type_dict[label] for i, label in enumerate(label_order)}
    label2id = {label: i for i, label in enumerate(label_order)}

    resolved_device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForImageClassification.from_pretrained(model_name)
    model.config.id2label = id2label
    model.config.label2id = label2id
    model.to(resolved_device)
    model.eval()

    logger.info("Loaded ViT model: %s on %s", model_name, resolved_device)
    return model, resolved_device


class SkinLesionClassifier:
    """Classify skin lesion images using a fine-tuned ViT model."""

    def __init__(self, model_name: str = "yuh0512/vit_skin_cancer_hf_v2"):
        self.model, self.device = load_vit_model(model_name=model_name)
        self.vit_transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def predict_vit(self, image: Image.Image) -> Tuple[str, float]:
        """Dự đoán bằng Vision Transformer."""
        image = image.convert("RGB")
        img_tensor = self.vit_transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(img_tensor)
            probs = torch.softmax(outputs.logits, dim=-1)
            pred_idx = probs.argmax(-1).item()
            confidence = probs[0, pred_idx].item()

        return self.model.config.id2label[pred_idx], confidence

    def predict(self, image_path: str) -> Tuple[str, float]:
        """Classify a local image file and return label + confidence."""
        try:
            image = Image.open(image_path)
            return self.predict_vit(image)
        except Exception as exc:
            logger.error("Error during classification: %s", exc)
            raise


# # Example Usage
# if __name__ == "__main__":
#     classifier = SkinLesionClassifier(model_name="yuh0512/vit_skin_cancer_hf_v2")
#     label, confidence = classifier.predict("./images/ISIC_0020840.jpg")
#     logger.info("Prediction: %s (confidence=%.4f)", label, confidence)
