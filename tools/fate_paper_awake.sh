#!/bin/bash
# Marker process for FATE paper keep-awake (pgrep: fate_paper_awake).
# Wrapped by `caffeinate -dims` from run_all.sh / launchd.
# macOS sleep has no "infinity" — loop a long sleep instead.
exec -a fate-paper-awake /bin/bash -c 'while true; do /bin/sleep 86400; done'
