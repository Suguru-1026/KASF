import random
import unittest
from krm_proto.predictor import encode_predictive_channel, decode_predictive_channel, verify_predictive_chunks


class PredictorTests(unittest.TestCase):
    def test_exact_roundtrip_orders_1_and_2(self):
        rng = random.Random(42)
        samples = [rng.randint(-(1 << 32), (1 << 32) - 1) for _ in range(1000)]
        for order in (1, 2):
            encoded = encode_predictive_channel(samples, order)
            self.assertEqual(decode_predictive_channel(encoded), samples)

    def test_short_and_empty_sequences(self):
        for samples in ([], [17], [17, -4]):
            for order in (1, 2):
                self.assertEqual(decode_predictive_channel(encode_predictive_channel(samples, order)), samples)

    def test_streaming_predictor_preserves_history_across_chunks(self):
        samples = [0, 1, 3, 6, 10, 15, -2, 7, 4, 99, -100]
        for order in (1, 2):
            report = verify_predictive_chunks([samples[:1], samples[1:4], [], samples[4:8], samples[8:]], order)
            self.assertTrue(report["exact"])
            self.assertEqual(report["sample_count"], len(samples))
            self.assertEqual(report["innovation_count"], len(samples) - min(order, len(samples)))


if __name__ == "__main__":
    unittest.main()
