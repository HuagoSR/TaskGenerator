import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from src.task_generator.v3_semantic_contract_v2 import (
    FinanceSemanticContractAdapter,
    FinanceSemanticContractResolver,
    TaskSemanticContractV2,
    to_review_contract,
)
from src.task_generator.v3_semantic_validity import (
    BlindRequirementReview,
    CandidateBlindReview,
    SemanticFinding,
    SemanticValidityGate,
    TeacherRubricReview,
)


class SemanticContractV2Tests(unittest.TestCase):
    def _blueprint(self, motif):
        if motif == "fan_in_reconciliation":
            files = [
                self._xlsx("bank_statement.xlsx", "Bank_Activity", ["Bank_ID", "Reference", "Amount"]),
                self._xlsx("cash_ledger.xlsx", "Cash_Ledger", ["Ledger_ID", "Reference", "Amount"]),
            ]
            deliverable = "cash_reconciliation.xlsx"
        elif motif == "cross_check_validation":
            files = [
                self._xlsx("purchase_orders.xlsx", "PO_Lines", ["PO_ID", "Item_ID", "Ordered_Qty", "Unit_Price"]),
                self._xlsx("goods_receipts.xlsx", "Receipt_Lines", ["Receipt_ID", "PO_ID", "Item_ID", "Received_Qty"]),
                self._xlsx("supplier_invoices.xlsx", "Invoice_Lines", ["Invoice_ID", "PO_ID", "Item_ID", "Invoiced_Qty", "Unit_Price"]),
            ]
            deliverable = "three_way_match_review.xlsx"
        else:
            files = [self._xlsx("expense_transactions.xlsx", "Transactions", [
                "Transaction_ID", "Employee_ID", "Category", "Amount", "Receipt_Available",
                "Approval_Level", "Business_Purpose",
            ]), {"file_name": "expense_policy.docx", "file_role": "reference_table", "sheet_specs": []}]
            deliverable = "expense_exception_memo.docx"
        return {
            "template_family": f"finance_{motif}_v1",
            "data_spec": {"reference_files": files, "data_relationships": []},
            "deliverable_spec": [{"file_name": deliverable, "file_role": "final_deliverable", "requirements": ["legacy"]}],
            "prompt_spec": {"visible_requirements": ["legacy"], "hidden_requirements": [], "style_constraints": []},
            "golden_plan": {"required_intermediate_states": [], "required_final_checks": []},
        }

    def _xlsx(self, name, sheet, columns):
        return {"file_name": name, "file_role": "source_data", "sheet_specs": [{
            "sheet_name": sheet,
            "row_count_target": 2,
            "columns": [{"name": value, "semantic_type": "identifier"} for value in columns],
        }]}

    def _write_workbook(self, path, sheet, rows):
        workbook = Workbook()
        ws = workbook.active
        ws.title = sheet
        ws.append(list(rows[0]))
        for row in rows[1:]:
            ws.append(list(row))
        workbook.save(path)

    def test_design_is_generator_owned_and_expense_adds_attendee_count(self):
        adapter = FinanceSemanticContractAdapter()
        prepared = adapter.prepare_blueprint(self._blueprint("policy_application"), "policy_application")
        columns = prepared["data_spec"]["reference_files"][0]["sheet_specs"][0]["columns"]
        self.assertIn("Attendee_Count", {item["name"] for item in columns})
        contract = adapter.design("task", "policy_application", prepared)
        self.assertEqual(contract.contract_origin, "generator_owned_v2")
        self.assertEqual(contract.lifecycle, "design")
        self.assertEqual(sum(item.weight for item in contract.rubric_bindings), 1.0)

    def test_cash_resolves_and_verifies_without_invented_balances(self):
        adapter = FinanceSemanticContractAdapter()
        contract = adapter.design("cash", "fan_in_reconciliation", self._blueprint("fan_in_reconciliation"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_workbook(root / "bank_statement.xlsx", "Bank_Activity", [
                ("Bank_ID", "Reference", "Amount"), ("B1", "R1", 10), ("B2", "R2", -3),
            ])
            self._write_workbook(root / "cash_ledger.xlsx", "Cash_Ledger", [
                ("Ledger_ID", "Reference", "Amount"), ("L1", "R1", 10), ("L2", "R3", -2),
            ])
            (root / "reconciliation_rules.docx").write_bytes(b"rules")
            resolved = FinanceSemanticContractResolver().resolve(contract, root)
            verified, report = FinanceSemanticContractResolver().verify(resolved)
        self.assertEqual(verified.lifecycle, "verified")
        self.assertEqual(report.decision, "pass")
        value = verified.claims[0].expected_result.value
        self.assertEqual(value["matched_count"], 1)
        self.assertNotIn("adjusted_balance", value)

    def test_three_way_and_expense_have_candidate_visible_rules(self):
        adapter = FinanceSemanticContractAdapter()
        for motif in ("cross_check_validation", "policy_application"):
            contract = adapter.design(motif, motif, self._blueprint(motif))
            rule_dependencies = [item for item in contract.dependencies if item.dependency_kind == "rule"]
            self.assertTrue(rule_dependencies)
            rule_locator_ids = {value for item in rule_dependencies for value in item.locator_ids}
            locators = {item.locator_id: item for item in contract.locators}
            self.assertTrue(all(locators[value].candidate_visible for value in rule_locator_ids))

    def test_three_way_duplicate_business_key_ignores_invoice_id_and_uses_both_quantity_variances(self):
        contract = FinanceSemanticContractAdapter().design(
            "three", "cross_check_validation", self._blueprint("cross_check_validation")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_workbook(root / "purchase_orders.xlsx", "PO_Lines", [
                ("PO_ID", "Item_ID", "Ordered_Qty", "Unit_Price"), ("P1", "I1", 10, 5),
            ])
            self._write_workbook(root / "goods_receipts.xlsx", "Receipt_Lines", [
                ("Receipt_ID", "PO_ID", "Item_ID", "Received_Qty"), ("R1", "P1", "I1", 9),
            ])
            self._write_workbook(root / "supplier_invoices.xlsx", "Invoice_Lines", [
                ("Invoice_ID", "PO_ID", "Item_ID", "Invoiced_Qty", "Unit_Price"),
                ("A", "P1", "I1", 9, 5), ("B", "P1", "I1", 9, 5),
            ])
            (root / "three_way_match_rules.docx").write_bytes(b"rules")
            resolved = FinanceSemanticContractResolver().resolve(contract, root)
        self.assertEqual(resolved.claims[0].expected_result.value["hold"], 2)

    def test_three_way_marks_every_member_of_duplicate_business_key(self):
        contract = FinanceSemanticContractAdapter().design(
            "duplicate", "cross_check_validation", self._blueprint("cross_check_validation")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_workbook(root / "purchase_orders.xlsx", "PO_Lines", [
                ("PO_ID", "Item_ID", "Ordered_Qty", "Unit_Price"), ("P1", "I1", 10, 5),
            ])
            self._write_workbook(root / "goods_receipts.xlsx", "Receipt_Lines", [
                ("Receipt_ID", "PO_ID", "Item_ID", "Received_Qty"), ("R1", "P1", "I1", 10),
            ])
            self._write_workbook(root / "supplier_invoices.xlsx", "Invoice_Lines", [
                ("Invoice_ID", "PO_ID", "Item_ID", "Invoiced_Qty", "Unit_Price"),
                ("A", "P1", "I1", 10, 5), ("B", "P1", "I1", 10, 5),
            ])
            (root / "three_way_match_rules.docx").write_bytes(b"rules")
            resolved = FinanceSemanticContractResolver().resolve(contract, root)
        self.assertEqual(resolved.claims[0].expected_result.value, {"clear": 0, "hold": 2, "investigate": 0})

    def test_review_bridge_preserves_precise_fields_and_fact_coverage(self):
        contract = FinanceSemanticContractAdapter().design(
            "task", "cross_check_validation", self._blueprint("cross_check_validation")
        )
        bridge = to_review_contract(contract)
        fields = {field for item in bridge.dependencies for field in item.field_names}
        self.assertIn("Received_Qty", fields)
        self.assertTrue(bridge.claims[0].rubric_criterion_ids)

    def test_llm_only_blocker_requires_secondary_then_agreement_revises(self):
        bridge = to_review_contract(FinanceSemanticContractAdapter().design(
            "task", "fan_in_reconciliation", self._blueprint("fan_in_reconciliation")
        ))
        finding = SemanticFinding(
            finding_code="ambiguous_requirement", severity="blocking", message="ambiguous",
            requirement_id="req_001", confidence=0.9, deterministic_corroboration=True,
        )
        blind = CandidateBlindReview(
            task_id="task", model="deepseek-v4-pro", provider="deepseek", created_at="now",
            prompt_package_sha256="a" * 64,
            requirement_reviews=[BlindRequirementReview(requirement_id="req_001", answerability="ambiguous", findings=[finding])],
        )
        teacher = TeacherRubricReview(
            task_id="task", model="deepseek-v4-pro", provider="deepseek", created_at="now",
            blind_review_sha256="b" * 64, teacher_truth_consistent=True,
            goldenrun_covers_requirements=True, rubric_fact_weight_ratio=0.7,
        )
        preliminary = SemanticValidityGate().build(bridge, blind, teacher, "blocking")
        self.assertEqual(preliminary.decision, "needs_secondary_review")
        secondary_blind = blind.model_copy(deep=True)
        secondary_blind.model = "gpt-5.4-pro"
        secondary_teacher = teacher.model_copy(deep=True)
        secondary_teacher.model = "gpt-5.4-pro"
        final = SemanticValidityGate().build(
            bridge, blind, teacher, "blocking",
            secondary_blind_review=secondary_blind,
            secondary_teacher_review=secondary_teacher,
        )
        self.assertEqual(final.decision, "revise")
        self.assertFalse(final.semantic_gate_pass)

    def test_warning_only_passes_with_advisories(self):
        bridge = to_review_contract(FinanceSemanticContractAdapter().design(
            "task", "fan_in_reconciliation", self._blueprint("fan_in_reconciliation")
        ))
        warning = SemanticFinding(
            finding_code="irrelevant_rubric_criterion", severity="warning", message="minor",
            requirement_id="req_001",
        )
        blind = CandidateBlindReview(
            task_id="task", model="deepseek-v4-pro", provider="deepseek", created_at="now",
            prompt_package_sha256="a" * 64,
            requirement_reviews=[BlindRequirementReview(requirement_id="req_001", answerability="supported")],
            findings=[warning],
        )
        teacher = TeacherRubricReview(
            task_id="task", model="deepseek-v4-pro", provider="deepseek", created_at="now",
            blind_review_sha256="b" * 64, teacher_truth_consistent=True,
            goldenrun_covers_requirements=True, rubric_fact_weight_ratio=0.7,
        )
        report = SemanticValidityGate().build(bridge, blind, teacher, "blocking")
        self.assertEqual(report.decision, "pass_with_advisories")
        self.assertTrue(report.semantic_gate_pass)


if __name__ == "__main__":
    unittest.main()
