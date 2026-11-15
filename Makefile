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

#################################################
# Edit the following to match your sources lists
#################################################


#Add iso code for any locales you want to support here (space separated)
# default is no locales
# LOCALES = af
LOCALES =

LRELEASE ?= lrelease
PYLUPDATE ?= pylupdate6
PYTHON ?= python3
UPLOAD_URL ?= https://plugins.qgis.org/plugins/RPC2/

# translation
SOURCES = \
	__init__.py \
	track_profile_2_web.py

TS_FILES = $(addprefix i18n/TrackProfile2web_,$(addsuffix .ts,$(LOCALES)))

PLUGINNAME = track_profile_2_web

PY_FILES = \
	__init__.py \
	track_profile_2_web.py

EXTRAS = metadata.txt icon.png track_profile_2_web.html LICENSE

EXTRA_DIRS =

COMPILED_RESOURCE_FILES =

PEP8EXCLUDE=pydev,conf.py,third_party,ui

# QGISDIR points to the location where your plugin should be installed.
# This varies by platform, relative to your HOME directory:
#	* Linux:
#	  .local/share/QGIS/QGIS4/profiles/default/python/plugins/
#	* Mac OS X:
#	  Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins
#	* Windows:
#	  AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins'

QGISDIR ?= $(HOME)/.local/share/QGIS/QGIS4/profiles/default/python/plugins

#################################################
# Normally you would not need to edit below here
#################################################

.PHONY: default
default:
	@echo "Targets: test, deploy, zip, upload, upload-existing, transup, transcompile, pylint"

compile: $(COMPILED_RESOURCE_FILES)

i18n/TrackProfile2web_%.ts: $(SOURCES)
	mkdir -p i18n
	$(PYLUPDATE) --no-obsolete $(SOURCES) --ts "$@"

test:
	@echo
	@echo "----------------------"
	@echo "BDD Test Suite"
	@echo "----------------------"
	python -m behave test/features

deploy: compile transcompile
	@echo
	@echo "------------------------------------------"
	@echo "Deploying plugin to your QGIS plugin directory."
	@echo "------------------------------------------"
	mkdir -p "$(QGISDIR)/$(PLUGINNAME)"
	cp -vf $(PY_FILES) "$(QGISDIR)/$(PLUGINNAME)"
	cp -vf $(EXTRAS) "$(QGISDIR)/$(PLUGINNAME)"
	if [ -d i18n ]; then cp -vfr i18n "$(QGISDIR)/$(PLUGINNAME)"; fi
	# Copy extra directories if any
	$(foreach EXTRA_DIR,$(EXTRA_DIRS),cp -R "$(EXTRA_DIR)" "$(QGISDIR)/$(PLUGINNAME)/";)


# The dclean target removes compiled python files from plugin directory
# also deletes any .git entry
dclean:
	@echo
	@echo "-----------------------------------"
	@echo "Removing any compiled python files."
	@echo "-----------------------------------"
	find "$(QGISDIR)/$(PLUGINNAME)" -iname "*.pyc" -delete
	find "$(QGISDIR)/$(PLUGINNAME)" -iname ".git" -prune -exec rm -Rf {} \;


derase:
	@echo
	@echo "-------------------------"
	@echo "Removing deployed plugin."
	@echo "-------------------------"
	rm -Rf "$(QGISDIR)/$(PLUGINNAME)"

zip: deploy dclean
	@echo
	@echo "---------------------------"
	@echo "Creating plugin zip bundle."
	@echo "---------------------------"
	# The zip target deploys the plugin and creates a zip file with the deployed
	# content. You can then upload the zip file on http://plugins.qgis.org
	rm -f $(PLUGINNAME).zip
	cd "$(QGISDIR)" && $(PYTHON) -m zipfile -c "$(CURDIR)/$(PLUGINNAME).zip" "$(PLUGINNAME)"

package: compile
	# Create a zip package of the plugin named $(PLUGINNAME).zip.
	# This requires use of git (your plugin development directory must be a
	# git repository).
	# To use, pass a valid commit or tag as follows:
	#   make package VERSION=Version_0.3.2
	@echo
	@echo "------------------------------------"
	@echo "Exporting plugin to zip package.	"
	@echo "------------------------------------"
	rm -f $(PLUGINNAME).zip
	git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(VERSION)
	echo "Created package: $(PLUGINNAME).zip"

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
	@echo
	@echo "------------------------------------------------"
	@echo "Updating translation files with any new strings."
	@echo "------------------------------------------------"

transcompile:
	@echo
	@echo "----------------------------------------"
	@echo "Compiled translation files to .qm files."
	@echo "----------------------------------------"
	$(foreach TRANSLATION,$(TS_FILES),$(LRELEASE) "$(TRANSLATION)" &&) true

transclean:
	@echo
	@echo "------------------------------------"
	@echo "Removing compiled translation files."
	@echo "------------------------------------"
	rm -f i18n/*.qm

clean:
	@echo
	@echo "------------------------------------"
	@echo "Removing uic and rcc generated files"
	@echo "------------------------------------"
	rm -f $(COMPILED_UI_FILES) $(COMPILED_RESOURCE_FILES)

pylint:
	@echo
	@echo "-----------------"
	@echo "Pylint violations"
	@echo "-----------------"
	@pylint --reports=n . || true
	@echo
	@echo "----------------------"
	@echo "If you get a 'no module named qgis.core' error, run pylint"
	@echo "from an environment configured for QGIS."
	@echo "----------------------"


# Run pep8 style checking
#http://pypi.python.org/pypi/pep8
pep8:
	@echo
	@echo "-----------"
	@echo "PEP8 issues"
	@echo "-----------"
	@pep8 --repeat --ignore=E203,E121,E122,E123,E124,E125,E126,E127,E128 --exclude $(PEP8EXCLUDE) . || true
	@echo "-----------"
	@echo "Ignored in PEP8 check:"
	@echo $(PEP8EXCLUDE)
