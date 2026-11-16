# 55GEEKS Oracle Always Free Capacity Monitor

This is the **public, code-only** capacity monitor for 55GEEKS Remote Support. It checks available compute host capacity in **us-sanjose-1**, availability domain **wQIc:US-SANJOSE-1-AD-1**.

**Status: configured in code only. Monitoring is not operational until the restricted OCI API credentials are transferred securely into this repository's GitHub Actions Secrets, the enable variable is set, and the first run succeeds.**

## Capabilities

- Scheduled checks every two hours (at 17 minutes past even UTC hours), plus manual execution.
- Checks 1 OCPU `VM.Standard.A1.Flex` at **6, 4, 2 and 1 GB** and `VM.Standard.E2.1.Micro`.
- When Oracle reports an available configuration, creates one GitHub **Issue** assigned to `miroooh`, avoiding duplicates while an alert issue remains open.
- No VM creation, resource provisioning, OCI policy updates, changes to other repositories, or paid runner upgrades.
- An AVAILABLE response does not reserve capacity. Always verify Always Free eligibility again before launching.

## Security

This repository is PUBLIC. Do not add credentials or internal hosting details to files or issues.

The workflow uses a dedicated OCI `55geeks-capacity-monitor` identity that has only:
`Allow group id <monitor-group-OCID> to manage compute-capacity-reports in tenancy`.
The four OCI identifiers/key values are stored as **GitHub Actions Secrets**, not in this repository. The workflow does not run on pull requests. The signing key is only used in an ephemeral runner and never printed to logs. Anyone who can edit the default-branch workflow can potentially use its secrets; restrict repository write permissions accordingly.

## One-time activation

The prior project already created, registered, and tested the restricted OCI monitor signing key **in Oracle Cloud Shell** under:
`$HOME/.55geeks-monitor/`.

After the [public runner preflight](../../actions/workflows/public-runner-preflight.yml) succeeds, open **Oracle Cloud Shell**, not HostGator, and run:

```bash
set -e
ACTIVATE="$(mktemp)"
trap 'rm -f "$ACTIVATE"' EXIT
curl -fsSL "https://raw.githubusercontent.com/miroooh/55geeks-oracle-monitor/3d76b4778186c62963e4ae1c6a31ddc3ca6571b8/scripts/activate-cloudshell.sh" -o "$ACTIVATE"
bash -n "$ACTIVATE"
bash "$ACTIVATE"
```

The pinned script verifies the existing restricted IAM policy and API key, uses a temporary GitHub device login, securely uploads four secrets to this public repository, sets `OCI_CAPACITY_MONITOR_ENABLED=true`, and requests the first capacity run. No private key is printed. GitHub login is isolated to a temporary configuration directory that is removed afterward.

To verify results, open [Actions](../../actions), select **Oracle Always Free capacity monitor**, and confirm the first capacity job completed successfully. If it fails, inspect the error; do not share tokens or signing keys.

GitHub issues are **public** here. GitHub email notifications depend on your account settings; turn on email notification for assigned issues and watch this repository for Issues if desired.

## Cost

GitHub currently documents standard `ubuntu-latest` hosted runners as free for public repositories. The workflow specifies **only** the standard runner. It creates no artifacts, caches or custom images and does not enable paid larger runners. This does not guarantee operation if an account-wide billing restriction prevents all jobs from starting.

Disable the schedule by setting Actions variable `OCI_CAPACITY_MONITOR_ENABLED=false`; it prevents jobs from executing, though GitHub still creates a skipped workflow run.
