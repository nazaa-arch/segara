"""
Modul Deteksi Anomali SEGARA.
Menyediakan deteksi anomali statistik berbasis:
1. Rolling Z-Score untuk parameter tunggal (Suhu, pH, Salinitas)
2. Isolation Forest untuk anomali multivariat sensor kelautan
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np
from sklearn.ensemble import IsolationForest


@dataclass
class AnomalyResult:
    is_anomaly: bool
    score: float
    method: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_anomaly": self.is_anomaly,
            "score": round(self.score, 3),
            "method": self.method,
            "details": self.details,
        }


class AnomalyDetector:
    def __init__(self, z_threshold: float = 3.0, contamination: float = 0.05, refit_every: int = 50):
        self.z_threshold = z_threshold
        self.contamination = contamination
        # State per node untuk data multi-parameter
        self._buffers: Dict[int, List[List[float]]] = {}
        self._models: Dict[int, Optional[IsolationForest]] = {}
        # Jumlah observasi sejak model terakhir dilatih, per node
        self._since_fit: Dict[int, int] = {}
        # Refit ~100-500 ms; untuk jendela 150 observasi, model diperbarui tiap 50
        # observasi baru (1/3 jendela) agar biaya per paket tetap rendah.
        self.refit_every = refit_every

    def add_observation(
        self,
        node_id: int,
        temperature: float,
        ph: float,
        salinity: float,
        turbidity: float,
    ) -> AnomalyResult:
        """
        Menganalisis observasi baru menggunakan kombinasi Z-score dan Isolation Forest.
        """
        features = [temperature, ph, salinity, turbidity]
        buffer = self._buffers.setdefault(node_id, [])
        buffer.append(features)

        # Pertahankan maksimum 150 observasi terakhir per node
        if len(buffer) > 150:
            buffer.pop(0)

        # Jika data masih sedikit (< 15 observasi), gunakan evaluasi awal
        if len(buffer) < 15:
            return AnomalyResult(
                is_anomaly=False,
                score=0.0,
                method="insufficient_data",
                details={"observations": len(buffer), "min_required": 15},
            )

        data_arr = np.array(buffer)

        # 1. Rolling Z-score untuk suhu
        mean_temp = np.mean(data_arr[:, 0])
        std_temp = np.std(data_arr[:, 0])
        z_score_temp = abs(temperature - mean_temp) / (std_temp + 1e-6)

        # 2. Fit / Predict Isolation Forest jika data cukup (>= 30 titik)
        is_forest_anomaly = False
        forest_score = 0.0

        if len(buffer) >= 30:
            # Latih ulang setiap `refit_every` observasi baru. Sebelumnya syaratnya
            # len(buffer) % 10 == 0, yang selalu benar begitu buffer penuh (150),
            # sehingga model dilatih ulang pada SETIAP paket (~150-200 ms per paket).
            since = self._since_fit.get(node_id, self.refit_every) + 1
            if self._models.get(node_id) is None or since >= self.refit_every:
                clf = IsolationForest(
                    contamination=self.contamination,
                    random_state=42,
                    n_estimators=50,
                )
                clf.fit(data_arr)
                self._models[node_id] = clf
                since = 0
            self._since_fit[node_id] = since

            model = self._models.get(node_id)
            if model is not None:
                current_vec = np.array([features])
                # predict() = -1 tepat saat decision_function() < 0; cukup satu kali penilaian
                decision_score = float(model.decision_function(current_vec)[0])
                is_forest_anomaly = decision_score < 0
                forest_score = -decision_score  # Nilai lebih tinggi = lebih anomali

        # Anomali dianggap terjadi jika Z-score suhu melampaui ambang batas ATAU Isolation Forest mendeteksi outlier
        is_anomaly = bool(z_score_temp > self.z_threshold or (is_forest_anomaly and forest_score > 0.15))
        effective_score = max(float(z_score_temp / self.z_threshold), float(forest_score * 2.0))

        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=effective_score,
            method="ensemble_zscore_isolation_forest",
            details={
                "temperature_z_score": round(float(z_score_temp), 2),
                "isolation_forest_anomaly": is_forest_anomaly,
                "isolation_forest_score": round(forest_score, 3),
                "temperature_mean": round(float(mean_temp), 2),
                "temperature_std": round(float(std_temp), 3),
            },
        )
