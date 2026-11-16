#!/usr/bin/env bash
# 55GEEKS: activate the PUBLIC GitHub Actions Oracle capacity monitor.
# Run ONLY in Oracle Cloud Shell. Reuse the existing restricted user and private key.
# Never print or commit the private key.
set -euo pipefail
umask 077
REPO='miroooh/55geeks-oracle-monitor'
DIR="$HOME/.55geeks-monitor"
MON_CONFIG="$DIR/monitor-config"
KEY="$DIR/api_key.pem"
FPR_FILE="$DIR/api_fingerprint.txt"
export PATH="$HOME/.local/bin:$PATH"
for cmd in oci gh python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Missing $cmd. Run in the existing Oracle Cloud Shell." >&2
    exit 1
  fi
done
if [[ ! -s "$MON_CONFIG" || ! -s "$KEY" || ! -s "$FPR_FILE" ]]; then
  echo 'ERROR: Existing restricted Oracle signing key or monitor config missing.' >&2
  echo 'Do not generate a new key or put administrator credentials in GitHub.' >&2
  exit 1
fi
read_conf() {
  awk -F= -v wanted="$1" '{
    k=$1; gsub(/[[:space:]]/,"",k);
    if(k==wanted){v=$2;gsub(/^[[:space:]]+|[[:space:]]+$/,"",v);print v;exit}
  }' "$MON_CONFIG"
}
TENANCY="$(read_conf tenancy)"
USER_ID="$(read_conf user)"
FPR="$(read_conf fingerprint)"
KEY_PATH="$(read_conf key_file)"
if [[ "$TENANCY" != ocid1.tenancy.* || "$USER_ID" != ocid1.user.* || "$KEY_PATH" != "$KEY" || "$FPR" != "$(cat "$FPR_FILE")" ]]; then
  echo 'ERROR: OCI signing key settings do not match the previously verified monitor.' >&2
  exit 1
fi
echo 'Checking Oracle key registration and existing restricted policy...'
REG=$(oci iam user api-key list --user-id "$USER_ID" --query "data[?fingerprint=='$FPR'].fingerprint | [0]" --raw-output)
[[ "$REG" == "$FPR" ]] || { echo 'ERROR: Oracle API key not registered.' >&2; exit 1; }
GID=$(oci iam group list --compartment-id "$TENANCY" --query "data[?name=='RemoteSupportCapacityMonitors'].id | [0]" --raw-output)
PID=$(oci iam policy list --compartment-id "$TENANCY" --query "data[?name=='55geeks-capacity-monitor-policy'].id | [0]" --raw-output)
[[ "$GID" == ocid1.group.* && "$PID" == ocid1.policy.* ]] || { echo 'ERROR: Restricted group or policy missing.' >&2; exit 1; }
POLICY_JSON=$(oci iam policy get --policy-id "$PID" --query 'data.statements' --output json)
POLICY_JSON="$POLICY_JSON" GID="$GID" python3 - <<'PY'
import json, os, sys
actual=json.loads(os.environ["POLICY_JSON"])
expected=["Allow group id "+os.environ["GID"]+" to manage compute-capacity-reports in tenancy"]
if actual != expected:
    sys.exit("ERROR: Unexpected IAM policy; do not publish this credential as a repository secret.")
PY
echo 'Testing restricted API access (capacity report only, no instance creation)...'
env -u OCI_CLI_KEY_CONTENT -u OCI_CLI_SECURITY_TOKEN_FILE -u OCI_CLI_USER \
    -u OCI_CLI_TENANCY -u OCI_CLI_FINGERPRINT -u OCI_CLI_KEY_FILE \
    oci compute compute-capacity-report create \
    --config-file "$MON_CONFIG" --profile DEFAULT --auth api_key \
    --region us-sanjose-1 --compartment-id "$TENANCY" \
    --availability-domain 'wQIc:US-SANJOSE-1-AD-1' \
    --shape-availabilities '[{"instanceShape":"VM.Standard.A1.Flex","instanceShapeConfig":{"ocpus":1,"memoryInGBs":6}}]' \
    >/dev/null
echo 'OCI_RESTRICTED_KEY=PASS'
GH_CONFIG_DIR="$(mktemp -d "$HOME/.55geeks-gh-session.XXXXXXXX")"
export GH_CONFIG_DIR
trap 'rm -rf "$GH_CONFIG_DIR"' EXIT
echo 'One-time GitHub authorization for public monitor repository:'
echo 'Open https://github.com/login/device when prompted.'
BROWSER=/bin/true gh auth login -h github.com --git-protocol https --web --skip-ssh-key -s repo,workflow
LOGIN="$(gh api user --jq '.login')"
[[ "$LOGIN" == miroooh ]] || { echo "ERROR: Authenticated as $LOGIN, expected miroooh." >&2; exit 1; }
IS_PRIVATE="$(gh repo view "$REPO" --json isPrivate --jq '.isPrivate')"
[[ "$IS_PRIVATE" == false ]] || { echo 'ERROR: Target repository must be the dedicated PUBLIC monitor.' >&2; exit 1; }
echo 'Uploading four OCI values to GitHub Actions SECRETS (never source code)...'
gh variable set OCI_CAPACITY_MONITOR_ENABLED -R "$REPO" --body false
printf '%s' "$TENANCY" | gh secret set OCI_MONITOR_TENANCY_OCID -R "$REPO"
printf '%s' "$USER_ID" | gh secret set OCI_MONITOR_USER_OCID -R "$REPO"
printf '%s' "$FPR" | gh secret set OCI_MONITOR_FINGERPRINT -R "$REPO"
gh secret set OCI_MONITOR_PRIVATE_KEY -R "$REPO" < "$KEY"
echo 'All four repository secrets saved. Activating two-hour free public runner checks...'
gh variable set OCI_CAPACITY_MONITOR_ENABLED -R "$REPO" --body true
gh workflow run oracle-capacity.yml -R "$REPO" --ref main
echo
echo 'PUBLIC_MONITOR_CONFIGURED: first GitHub Actions run requested.'
echo 'Open https://github.com/miroooh/55geeks-oracle-monitor/actions'
echo 'Check the first run for SUCCESS. Alerts are GitHub Issues assigned to miroooh.'
echo 'Enable GitHub email notifications for assigned issues to get email alerts.'
echo 'No Oracle VM or paid resource was created.'
