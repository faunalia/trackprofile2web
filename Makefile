#/***************************************************************************
# TrackProfile2Web
#
# Leaflet interactive web profiles.
#							 -------------------
#		begin				: 2019-05-24
#		git sha				: $Format:%H$
#		copyright			: (C) 2019 by Matteo Ghetta
#		email				: matteo.ghetta@faunalia.eu
# ***************************************************************************/
#
#/***************************************************************************
# *																		 *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or	 *
# *   (at your option) any later version.								   *
# *																		 *
# ***************************************************************************/

LOCALES =
LRELEASE ?= lrelease
PYLUPDATE ?= pylupdate6
PYTHON ?= python3
UPLOAD_URL ?= https://plugins.qgis.org/plugins/RPC2/

PY_FILES = \
	__init__.py \
	track_profile_2_web.py

TS_FILES = $(addprefix i18n/TrackProfile2web_,$(addsuffix .ts,$(LOCALES)))
PLUGINNAME = track_profile_2_web
EXTRAS = metadata.txt icon.png track_profile_2_web.html LICENSE

.PHONY: default test zip upload upload-existing transup transcompile transclean
default:
	@echo "Targets: test, zip, upload, upload-existing, transup, transcompile, transclean"

i18n/TrackProfile2web_%.ts: $(PY_FILES)
	mkdir -p i18n
	$(PYLUPDATE) --no-obsolete $(PY_FILES) --ts "$@"

test:
	$(PYTHON) -m behave test/features

zip: transcompile
	@$(PYTHON) -c "$$(printf '%s\n' \
	    'from pathlib import Path' \
	    'import sys, zipfile' \
	    'name, *files = sys.argv[1:]' \
	    'paths = [Path(file) for file in files]' \
	    'i18n = Path("i18n")' \
	    'if i18n.is_dir():' \
	    '    paths.extend(path for path in (i18n, *i18n.rglob("*"))' \
	    '                 if all(part.lower() != ".git" for part in path.parts)' \
	    '                 and not path.name.lower().endswith(".pyc"))' \
	    'with zipfile.ZipFile(name + ".zip", "w", zipfile.ZIP_DEFLATED) as archive:' \
	    '    for path in paths:' \
	    '        archive.write(path, Path(name) / path)' \
	)" "$(PLUGINNAME)" $(PY_FILES) $(EXTRAS)

upload: zip
	$(MAKE) upload-existing

upload-existing:
	@echo
	@echo "-------------------------------------"
	@echo "Uploading plugin to QGIS Plugin repo."
	@echo "-------------------------------------"
	@$(PYTHON) -c "$$(printf '%s\n' \
	    'import getpass, sys, xmlrpc.client' \
	    'from urllib.parse import quote, urlsplit, urlunsplit' \
	    'url = urlsplit(sys.argv[2])' \
	    'if not url.hostname or url.username is not None or url.password is not None:' \
	    '    sys.exit("Invalid upload URL")' \
	    'if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")):' \
	    '    sys.exit("Upload requires HTTPS except for a local repository")' \
	    'default_user = getpass.getuser()' \
	    'username = input("Please enter user name [%s]: " % default_user) or default_user' \
	    'password = getpass.getpass()' \
	    'auth = "%s:%s@" % (quote(username, safe=""), quote(password, safe=""))' \
	    'address = urlunsplit((url.scheme, auth + url.netloc, url.path, url.query, url.fragment))' \
	    'try:' \
	    '    with open(sys.argv[1], "rb") as handle:' \
	    '        package = xmlrpc.client.Binary(handle.read())' \
	    '    with xmlrpc.client.ServerProxy(address) as server:' \
	    '        plugin_id, version_id = server.plugin.upload(package)' \
	    '    print("Plugin ID: %s" % plugin_id)' \
	    '    print("Version ID: %s" % version_id)' \
	    'except xmlrpc.client.ProtocolError as err:' \
	    '    sys.exit("Upload failed: HTTP %d %s" % (err.errcode, err.errmsg))' \
	    'except (xmlrpc.client.Fault, OSError) as err:' \
	    '    sys.exit("Upload failed: %s" % err)' \
	)" "$(PLUGINNAME).zip" "$(UPLOAD_URL)"

transup: $(TS_FILES)

transcompile:
	$(foreach TRANSLATION,$(TS_FILES),$(LRELEASE) "$(TRANSLATION)" &&) true

transclean:
	rm -f i18n/*.qm
