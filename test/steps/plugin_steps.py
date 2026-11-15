import base64
import configparser
import os
import shlex
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xmlrpc.client import Fault
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from behave import given, then, when


ROOT = Path(__file__).resolve().parents[2]


@given("the plugin metadata")
def read_metadata(context):
    context.metadata = configparser.ConfigParser()
    context.metadata.optionxform = str
    assert context.metadata.read(ROOT / "metadata.txt", encoding="utf-8")


@then("all mandatory metadata fields are present")
def check_metadata(context):
    assert context.metadata.has_section("general")
    for field in ("name", "description", "version", "qgisMinimumVersion", "email", "author"):
        assert context.metadata.has_option("general", field), field


@given("QGIS is initialized")
def init_qgis(context):
    from support.hooks import qgis_app
    qgis_app()


@then("the GDAL, OGR and PostgreSQL providers are available")
def check_providers(context):
    from qgis.core import QgsProviderRegistry
    assert {"gdal", "ogr", "postgres"} <= set(QgsProviderRegistry.instance().providerList())


@when("I {action} the dialog")
def finish_dialog(context, action):
    if action == "accept":
        context.dialog.accept()
    else:
        assert action == "reject"
        context.dialog.reject()


@then("the dialog result is {result}")
def check_dialog_result(context, result):
    from qgis.PyQt.QtWidgets import QDialog
    expected = {"accepted": QDialog.DialogCode.Accepted, "rejected": QDialog.DialogCode.Rejected}
    assert context.dialog.result() == expected[result]


class AuthenticatedHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/plugins/RPC2/",)

    def do_POST(self):
        if self.headers.get("Authorization") != self.server.expected_auth:
            self.send_error(401, "Unauthorized")
            return
        super().do_POST()


@given("a plugin package and a local repository")
def local_repository(context):
    if os.name != "posix":
        context.scenario.skip("Makefile upload requires a Unix shell")
        return
    context.package_dir = Path(context.tempdir.name)
    shutil.copy(ROOT / "Makefile", context.package_dir / "Makefile")
    context.package = context.package_dir / "track_profile_2_web.zip"
    context.package.write_bytes(b"test zip")
    username, password = "user@example.test", "p@ss:word"
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    context.server = SimpleXMLRPCServer(
        ("127.0.0.1", 0), requestHandler=AuthenticatedHandler, logRequests=False
    )
    context.server.expected_auth = f"Basic {token}"
    context.received = []
    context.server.register_function(
        lambda data: (context.received.append(data.data) or [12, 34]), "plugin.upload"
    )
    context.server_thread = threading.Thread(target=context.server.serve_forever)
    context.server_thread.start()
    context.options = SimpleNamespace(
        username=username, password=password,
        server="127.0.0.1", port=context.server.server_address[1]
    )


def upload_package(context):
    url = f"http://127.0.0.1:{context.options.port}/plugins/RPC2/"
    context.result = subprocess.run(
        ["make", "-o", "zip", "upload", f"UPLOAD_URL={url}", f"PYTHON={shlex.quote(sys.executable)}"],
        cwd=context.package_dir, input=f"{context.options.username}\n{context.options.password}\n",
        capture_output=True, text=True, start_new_session=True, timeout=30
    )


@when("I upload the package with valid credentials")
def upload_with_valid_credentials(context):
    upload_package(context)


@then("the repository receives the package and returns its identifiers")
def check_uploaded_package(context):
    assert context.result.returncode == 0, context.result.stderr
    assert context.received == [b"test zip"]
    assert "Plugin ID: 12" in context.result.stdout
    assert "Version ID: 34" in context.result.stdout


@when("I upload the package with invalid credentials")
def upload_with_invalid_credentials(context):
    context.options.password = "wrong@password"
    upload_package(context)


@then("the upload fails without exposing credentials")
def check_authentication_failure(context):
    assert context.result.returncode != 0
    assert context.received == []
    assert "HTTP 401" in context.result.stderr
    output = context.result.stdout + context.result.stderr
    assert "p@ss:word" not in output
    assert context.options.password not in output


@when("the repository rejects the uploaded package")
def reject_package(context):
    def reject(data):
        raise Fault(10, "Plugin rejected")

    context.server.register_function(reject, "plugin.upload")
    upload_package(context)


@then("the upload reports the rejection")
def check_rejection(context):
    assert context.result.returncode != 0
    assert "Plugin rejected" in context.result.stderr


@when("I upload a missing package with Make")
def upload_missing_package(context):
    if os.name != "posix":
        context.scenario.skip("Makefile upload requires a Unix shell")
        return
    package_dir = Path(context.tempdir.name)
    shutil.copy(ROOT / "Makefile", package_dir / "Makefile")
    context.result = subprocess.run(
        ["make", "upload-existing", f"PYTHON={shlex.quote(sys.executable)}"],
        cwd=package_dir, input="user\npassword\n", capture_output=True, text=True,
        start_new_session=True, timeout=30
    )


@then("the upload command reports failure")
def check_missing_package(context):
    assert context.result.returncode != 0
    assert "Upload failed" in context.result.stderr


@when("I configure an insecure remote upload URL")
def insecure_upload_url(context):
    if os.name != "posix":
        context.scenario.skip("Makefile upload requires a Unix shell")
        return
    package_dir = Path(context.tempdir.name)
    shutil.copy(ROOT / "Makefile", package_dir / "Makefile")
    context.result = subprocess.run(
        ["make", "upload-existing", "UPLOAD_URL=http://example.test/plugins/RPC2/",
         f"PYTHON={shlex.quote(sys.executable)}"],
        cwd=package_dir, input="user\npassword\n", capture_output=True, text=True,
        start_new_session=True, timeout=30
    )


@then("the upload rejects the URL before requesting credentials")
def check_insecure_upload_url(context):
    assert context.result.returncode != 0
    assert "Upload requires HTTPS" in context.result.stderr
    assert "Please enter user name" not in context.result.stdout


@given("a plugin ready for packaging")
def prepare_package(context):
    if os.name != "posix":
        context.scenario.skip("Makefile packaging requires a Unix shell")
        return
    context.package_dir = Path(context.tempdir.name)
    for name in ("Makefile", "__init__.py", "track_profile_2_web.py",
                 "metadata.txt", "icon.png", "track_profile_2_web.html", "LICENSE"):
        shutil.copy(ROOT / name, context.package_dir / name)
    deployed = context.package_dir / "deploy" / "track_profile_2_web"
    deployed.mkdir(parents=True)
    (deployed / "stale.txt").write_text("unchanged")
    i18n = context.package_dir / "i18n"
    i18n.mkdir()
    (i18n / "unused.qm").write_text("unused")


@when("I build the plugin package")
def build_package(context):
    subprocess.run(
        ["make", "zip", "QGISDIR=deploy", f"PYTHON={shlex.quote(sys.executable)}"],
        cwd=context.package_dir, check=True
    )


@then("the ZIP contains only the plugin files")
def check_package(context):
    files = ("__init__.py", "track_profile_2_web.py", "metadata.txt",
             "icon.png", "track_profile_2_web.html", "LICENSE")
    with zipfile.ZipFile(context.package_dir / "track_profile_2_web.zip") as archive:
        assert set(archive.namelist()) == {f"track_profile_2_web/{name}" for name in files}
        assert archive.testzip() is None


@then("the deployed plugin is unchanged")
def check_deployed_plugin(context):
    deployed = context.package_dir / "deploy" / "track_profile_2_web"
    assert [path.name for path in deployed.iterdir()] == ["stale.txt"]
    assert (deployed / "stale.txt").read_text() == "unchanged"
