from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

URL = "/api/bug-reports"


def client():
    return TestClient(app)


def test_paste_submission_is_stored():
    with client() as c:
        r = c.post(URL, data={"title": "Crash", "description": "App crashes on save", "stack_trace": "NullPointerException\n  at Foo.bar"})
        assert r.status_code == 201
        body = r.json()
        assert body["input_method"] == "paste" and body["status"] == "submitted"
        got = c.get(f"{URL}/{body['id']}").json()
        assert got["stack_trace"].startswith("NullPointerException")


def test_description_required():
    with client() as c:
        r = c.post(URL, data={"stack_trace": "trace only"})
        assert r.status_code == 422


def test_file_upload_replaces_field_and_is_recorded():
    with client() as c:
        r = c.post(URL, data={"description": "Log attached"}, files={"error_log_file": ("app.log", b"ERROR something failed", "text/plain")})
        assert r.status_code == 201
        body = r.json()
        assert body["input_method"] == "upload"
        assert body["error_log"] == "ERROR something failed"
        assert body["files"][0]["file_type"] == "log"
        assert body["files"][0]["field"] == "error_log"


def test_description_from_file():
    with client() as c:
        r = c.post(URL, files={"description_file": ("bug.txt", b"Button does nothing", "text/plain")})
        assert r.status_code == 201
        assert r.json()["description"] == "Button does nothing"


def test_unsupported_extension_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "x"}, files={"error_log_file": ("run.exe", b"abc", "application/octet-stream")})
        assert r.status_code == 415


def test_oversized_file_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "x"}, files={"error_log_file": ("big.log", b"a" * 2000, "text/plain")})
        assert r.status_code == 413


def test_oversized_pasted_text_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "a" * 2000})
        assert r.status_code == 413


def test_invalid_json_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "x"}, files={"error_log_file": ("data.json", b"{not json", "application/json")})
        assert r.status_code == 422


def test_empty_file_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "x"}, files={"error_log_file": ("empty.log", b"   ", "text/plain")})
        assert r.status_code == 422


def test_binary_file_rejected():
    with client() as c:
        r = c.post(URL, data={"description": "x"}, files={"error_log_file": ("a.log", b"ab\x00cd", "text/plain")})
        assert r.status_code == 422


def test_list_and_404():
    with client() as c:
        assert c.get(URL).status_code == 200
        assert c.get(f"{URL}/999999").status_code == 404
