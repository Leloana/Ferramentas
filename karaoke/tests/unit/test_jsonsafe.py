"""jsonable: mensagem de fim de jogo e gravação sempre serializáveis."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from utils.jsonsafe import jsonable  # noqa: E402


class JsonableTest(unittest.TestCase):
    def test_numpy_and_odd_values_become_json(self):
        msg = {"score": np.float32(90.25), "n": np.int64(3), "ok": np.bool_(True),
               "arr": np.array([1.5, 2.5]), "t": (1, 2), "nan": float("nan"), 7: object()}
        out = json.loads(json.dumps(jsonable(msg)))
        self.assertAlmostEqual(out["score"], 90.25, places=4)
        self.assertEqual(out["n"], 3)
        self.assertIs(out["ok"], True)
        self.assertEqual(out["arr"], [1.5, 2.5])
        self.assertEqual(out["t"], [1, 2])
        self.assertIsNone(out["nan"])
        self.assertIsInstance(out["7"], str)
