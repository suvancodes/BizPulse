import unittest
from types import SimpleNamespace

import pandas as pd
from flask import Flask, g

import backend.data_store as data_store
from app import app
from backend.auth import safe_next_url, seal_session, unseal_session
from routes import (
    validate_inventory_rows,
    validate_product_rows,
    validate_transaction_rows,
)


class AuthAndStorageTests(unittest.TestCase):
    def test_public_and_protected_routes(self):
        client = app.test_client()

        self.assertEqual(client.get("/").status_code, 200)
        response = client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_auth_forms_require_csrf(self):
        client = app.test_client()
        response = client.post(
            "/auth/login",
            data={"email": "user@example.com", "password": "password"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"session expired", response.data.lower())

    def test_next_url_rejects_external_redirects(self):
        with app.test_request_context("/"):
            self.assertEqual(
                safe_next_url("https://example.com"),
                "/dashboard",
            )
            self.assertEqual(safe_next_url("/analytics"), "/analytics")

    def test_session_payload_is_encrypted(self):
        payload = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        }
        sealed = seal_session(payload)

        self.assertNotIn("access-token", sealed)
        self.assertEqual(unseal_session(sealed), payload)

    def test_import_validation_rejects_invalid_and_duplicate_rows(self):
        transactions = pd.DataFrame([
            {
                "transaction_id": "T-1",
                "date": "not-a-date",
                "quantity": 0,
                "unit_price": -1,
                "cost_price": 1,
            },
            {
                "transaction_id": "T-1",
                "date": "2026-01-01",
                "quantity": 1,
                "unit_price": 1,
                "cost_price": 1,
            },
        ])
        products = pd.DataFrame([
            {"product_id": "P-1", "product_name": "One"},
            {"product_id": "P-1", "product_name": "Duplicate"},
        ])
        inventory = pd.DataFrame([
            {
                "product_id": "P-1",
                "date": "not-a-date",
                "stock_quantity": -1,
                "reorder_level": 0,
            },
        ])

        self.assertTrue(validate_transaction_rows(transactions))
        self.assertTrue(validate_product_rows(products))
        self.assertTrue(validate_inventory_rows(inventory))

    def test_transaction_mapping_is_user_scoped(self):
        class Response:
            data = []

        class Query:
            def __init__(self):
                self.operations = []

            def delete(self):
                self.operations.append(("delete",))
                return self

            def eq(self, field, value):
                self.operations.append(("eq", field, value))
                return self

            def insert(self, records):
                self.operations.append(("insert", records))
                return self

            def execute(self):
                return Response()

        class Client:
            def __init__(self):
                self.query = Query()

            def table(self, name):
                self.table_name = name
                return self.query

        client = Client()
        original_client = data_store.get_supabase_client
        data_store.get_supabase_client = lambda: client

        try:
            with Flask(__name__).test_request_context("/"):
                g.current_user = SimpleNamespace(id="user-1")
                data_store.replace_transactions(pd.DataFrame([{
                    "transaction_id": "T-1",
                    "date": "2026-01-01",
                    "customer_id": "C-1",
                    "product_id": "P-1",
                    "product_name": "Product",
                    "category": "Category",
                    "quantity": 1,
                    "unit_price": 10,
                    "cost_price": 5,
                    "region": "North",
                }]))
        finally:
            data_store.get_supabase_client = original_client

        insert_operation = client.query.operations[-1]
        self.assertEqual(insert_operation[0], "insert")
        self.assertEqual(insert_operation[1][0]["user_id"], "user-1")


if __name__ == "__main__":
    unittest.main()
