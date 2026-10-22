"""Тесты бизнес-ядра: стандартная библиотека, запуск `python -m unittest discover -s tests`."""
import unittest
from datetime import date

from app.domain import mocks
from app.domain.calc import annuity_payment
from app.domain.pipeline import enrich, evaluate, validate
from app.domain.products import PRODUCTS_BY_CODE, class_for_score
from app.domain.statemachine import FINAL_STATUSES, InvalidTransition, ensure_transition, transition_allowed

WC = PRODUCTS_BY_CODE["working_capital"]


def run(inn, **overrides):
    data = dict(product_code="working_capital", amount=5_000_000, term_months=12, purpose="Закупка товара",
                inn=inn, revenue=14_000_000, revenue_prev=13_000_000)
    data.update(overrides)
    v = validate(data, WC)
    checks = enrich(inn)
    return v, evaluate(data, WC, checks)


class ScenarioTests(unittest.TestCase):
    def test_a_auto_approved(self):  # Север-Строй
        _, r = run("7701000001", revenue=60_000_000, revenue_prev=50_000_000)
        self.assertEqual(r["scoring"]["klass"], "A")
        self.assertEqual(r["decision"]["outcome"], "approved")
        self.assertEqual(r["decision"]["offer"]["amount"], 5_000_000)
        self.assertEqual(r["decision"]["offer"]["rate"], 18.0)

    def test_b_counter_offer_matches_slide_example(self):  # Ромашка-Опт
        _, r = run("7701000002")
        pts = {f["key"]: f["points"] for f in r["scoring"]["factors"]}
        self.assertEqual(pts, {"business_age": 8, "revenue_growth": 12, "debt_load": 14,
                               "credit_history": 17, "tax_status": 10, "amount_to_revenue": 0})
        self.assertEqual(r["scoring"]["score"], 61)
        self.assertEqual(r["scoring"]["klass"], "B")
        d = r["decision"]
        self.assertEqual(d["outcome"], "counter_offer")
        self.assertEqual(d["offer"], dict(amount=3_500_000, term_months=12, rate=21.0))

    def test_missing_revenue_needs_data(self):  # ИП Тестов
        v = validate(dict(product_code="working_capital", amount=1_000_000, term_months=12, purpose="x",
                          inn="7701000003", revenue=None, revenue_prev=None), WC)
        self.assertIn("revenue", v["missing"])
        self.assertIn("Выручка за последний год", v["missing_labels"])

    def test_c_manual_review(self):  # Гранит-Сервис
        _, r = run("7701000004", revenue=20_000_000, revenue_prev=22_000_000)
        self.assertEqual(r["scoring"]["score"], 45)
        self.assertEqual(r["scoring"]["klass"], "C")
        self.assertEqual(r["decision"]["outcome"], "manual_review")

    def test_overdue_90_rejected_by_stop_factor(self):  # Лотос-Трейд
        _, r = run("7701000005", revenue=60_000_000, revenue_prev=50_000_000)
        self.assertEqual(r["decision"]["outcome"], "rejected")
        self.assertEqual(r["scoring"]["stop_factors"][0]["code"], "overdue_90")

    def test_liquidation_rejected_by_stop_factor(self):  # Вектор-Логистика
        _, r = run("7701000006", revenue=60_000_000, revenue_prev=50_000_000)
        self.assertEqual(r["decision"]["outcome"], "rejected")
        self.assertEqual(r["scoring"]["stop_factors"][0]["code"], "company_liquidating")

    def test_bki_timeout_goes_to_manual_review(self):  # Тайм-Аут
        checks = enrich("7701000007")
        self.assertEqual(checks["bki"]["status"], "timeout")
        self.assertEqual(checks["bki"]["attempts"], 3)  # 1 + 2 повтора
        _, r = run("7701000007", revenue=60_000_000, revenue_prev=50_000_000)
        self.assertEqual(r["decision"]["outcome"], "manual_review")
        self.assertEqual(r["decision"]["reasons"][0]["code"], "source_unavailable")

    def test_unknown_company_in_application_name_mismatch(self):
        data = dict(product_code="working_capital", amount=1_000_000, term_months=12, purpose="x", inn="7701000001",
                    revenue=60_000_000, revenue_prev=50_000_000, company_name="ООО «Другое»")
        r = evaluate(data, WC, enrich("7701000001"))
        self.assertEqual(r["decision"]["outcome"], "rejected")
        self.assertEqual(r["scoring"]["stop_factors"][0]["code"], "company_data_mismatch")

    def test_invalid_inn_not_found(self):
        checks = enrich("123")
        self.assertEqual(checks["egrul"]["status"], "not_found")

    def test_amount_outside_product_limits(self):
        v = validate(dict(product_code="working_capital", amount=100, term_months=12, purpose="x", inn="7701000001",
                          revenue=1, revenue_prev=1), WC)
        self.assertTrue(v["errors"])


class UnitTests(unittest.TestCase):
    def test_classes_boundaries(self):
        self.assertEqual([class_for_score(s)["klass"] for s in (100, 75, 74, 55, 54, 40, 39, 0)],
                         ["A", "A", "B", "B", "C", "C", "D", "D"])

    def test_annuity(self):
        self.assertAlmostEqual(annuity_payment(1_200_000, 0, 12), 100_000)
        self.assertAlmostEqual(annuity_payment(5_000_000, 18, 12), 458_400, delta=100)

    def test_total_max_is_100(self):
        from app.domain.scoring import compute_score
        r = compute_score(amount=1, term_months=12, revenue=10**9, revenue_prev=1, base_rate=18,
                          egrul=mocks.egrul("7701000001"), fns=mocks.fns("7701000001"), bki=mocks.bki("7701000001"),
                          today=date.today())
        self.assertEqual(r["score"], 100)
        self.assertEqual(sum(f["max"] for f in r["factors"]), 100)

    def test_mock_dates_deterministic(self):
        today = date(2026, 10, 22)
        e1 = mocks.egrul("7701000002", today=today)
        e2 = mocks.egrul("7701000002", today=today)
        self.assertEqual(e1, e2)
        age = (today - date.fromisoformat(e1["registration_date"])).days / 365.25
        self.assertAlmostEqual(age, 1.5, delta=0.01)


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self):
        path = ["draft", "submitted", "checking", "enrichment", "scoring", "decision", "approved",
                "offer_accepted", "signed", "disbursed"]
        for a, b in zip(path, path[1:]):
            self.assertTrue(transition_allowed(a, b), (a, b))

    def test_needs_data_loop(self):
        self.assertTrue(transition_allowed("checking", "needs_data"))
        self.assertTrue(transition_allowed("needs_data", "submitted"))

    def test_forbidden(self):
        for a, b in [("draft", "approved"), ("rejected", "approved"), ("disbursed", "withdrawn"),
                     ("approved", "disbursed"), ("scoring", "approved")]:
            with self.assertRaises(InvalidTransition):
                ensure_transition(a, b)

    def test_finals(self):
        self.assertEqual(FINAL_STATUSES, {"rejected", "disbursed", "withdrawn", "expired"})


if __name__ == "__main__":
    unittest.main()
