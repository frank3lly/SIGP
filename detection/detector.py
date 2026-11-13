import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

TARGET_VEHICLE_CLASSES: Dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass(frozen=True)
class VehicleDetection:
    """Represents a single detected vehicle bounding box."""

    box: Tuple[float, float, float, float]
    class_id: int
    class_name: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert detection to standard dictionary."""
        return {
            "box": [round(coord, 2) for coord in self.box],
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
        }


class VehicleDetector:
    """Ultra-lightweight ONNX Runtime vehicle detector eliminating PyTorch runtime dependencies."""

    def __init__(
        self,
        model_path: Union[str, Path] = "yolov8n.onnx",
        device: Optional[str] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        **kwargs: Any,
    ) -> None:
        model_str = str(model_path)
        if model_str.endswith(".pt"):
            onnx_candidate = Path(model_str).with_suffix(".onnx")
            if onnx_candidate.exists():
                self.model_path = onnx_candidate
            elif Path("yolov8n.onnx").exists():
                self.model_path = Path("yolov8n.onnx")
            else:
                self.model_path = Path(model_path)
        else:
            self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(f"ONNX model file not found at: {self.model_path}")

        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = "cpu"

        # Configure deterministic single-thread session for minimal RAM footprint
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

        # Execute single warmup pass to warm instruction caches
        warmup_blob = np.zeros((1, 3, 640, 640), dtype=np.float32)
        self.session.run(None, {self.input_name: warmup_blob})
        logger.info(f"VehicleDetector (ONNX Runtime) initialized successfully from '{self.model_path}'.")

    def _prepare_image(self, image: np.ndarray) -> np.ndarray:
        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("Input image must be a non-empty numpy.ndarray")

        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.ndim == 3:
            channels = image.shape[2]
            if channels == 1:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            elif channels == 3:
                return image
            elif channels == 4:
                return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        raise ValueError(f"Unsupported image shape for detection: {image.shape}")

    def _letterbox(
        self,
        image: np.ndarray,
        target_size: int = 640,
    ) -> Tuple[np.ndarray, float, float, float]:
        orig_h, orig_w = image.shape[:2]
        r = min(target_size / orig_h, target_size / orig_w)
        nw, nh = int(round(orig_w * r)), int(round(orig_h * r))
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
        pad_x = (target_size - nw) / 2.0
        pad_y = (target_size - nh) / 2.0
        top = int(round(pad_y))
        left = int(round(pad_x))
        canvas[top : top + nh, left : left + nw] = resized
        return canvas, r, pad_x, pad_y

    def detect(
        self,
        image: np.ndarray,
        conf_threshold: Optional[float] = None,
        imgsz: Optional[Any] = None,
    ) -> Tuple[List[VehicleDetection], float]:
        t0 = time.time()
        prepared_img = self._prepare_image(image)
        orig_h, orig_w = prepared_img.shape[:2]
        effective_conf = conf_threshold if conf_threshold is not None else self.conf_threshold

        # 1. Preprocess: Generate letterbox normalized NCHW blob (640x640)
        canvas, r, pad_x, pad_y = self._letterbox(prepared_img, target_size=640)
        blob = cv2.dnn.blobFromImage(
            canvas,
            scalefactor=1.0 / 255.0,
            size=(640, 640),
            swapRB=True,
            crop=False,
        )

        # 2. Execute inference
        outputs = self.session.run(None, {self.input_name: blob})
        preds = outputs[0][0]  # Shape: (84, 8400)
        preds = np.transpose(preds, (1, 0))  # Shape: (8400, 84)

        # 3. Filter candidate boxes for vehicle classes
        boxes: List[List[int]] = []
        confidences: List[float] = []
        class_ids: List[int] = []

        for row in preds:
            class_scores = row[4:]
            cid = int(np.argmax(class_scores))
            conf = float(class_scores[cid])

            if conf >= effective_conf and cid in TARGET_VEHICLE_CLASSES:
                cx, cy, bw, bh = row[0:4]
                x1 = (cx - bw / 2.0 - pad_x) / r
                y1 = (cy - bh / 2.0 - pad_y) / r
                w_box = bw / r
                h_box = bh / r

                boxes.append([int(x1), int(y1), int(w_box), int(h_box)])
                confidences.append(conf)
                class_ids.append(cid)

        # 4. Apply Non-Maximum Suppression (NMS)
        detections: List[VehicleDetection] = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(
                bboxes=boxes,
                scores=confidences,
                score_threshold=effective_conf,
                nms_threshold=self.iou_threshold,
            )
            for idx in indices:
                i = int(idx)
                bx, by, bw, bh = boxes[i]
                cid = class_ids[i]
                conf = confidences[i]
                # Clamp coordinates to original frame bounds
                x1_clamped = max(0.0, min(float(bx), float(orig_w)))
                y1_clamped = max(0.0, min(float(by), float(orig_h)))
                x2_clamped = max(0.0, min(float(bx + bw), float(orig_w)))
                y2_clamped = max(0.0, min(float(by + bh), float(orig_h)))

                detections.append(
                    VehicleDetection(
                        box=(x1_clamped, y1_clamped, x2_clamped, y2_clamped),
                        class_id=cid,
                        class_name=TARGET_VEHICLE_CLASSES[cid],
                        confidence=conf,
                    )
                )

        latency_ms = (time.time() - t0) * 1000.0
        return detections, round(latency_ms, 2)
