#!/usr/bin/env bash
# Prepare a running wp-env site for the evals: pretty permalinks (the MCP
# endpoint lives under /wp-json/), the two test identities and fresh
# Application Passwords, then write the environment variables pytest reads.
#
# Usage: scripts/ci-setup.sh [output-file]
#   output-file defaults to $GITHUB_ENV in GitHub Actions, else .env.wp-env
#   (gitignored). Variables already in the environment win over .env, so
#   locally: set -a; source .env.wp-env; set +a; pytest
#
# Re-runnable: existing users are kept, their "evals" Application Passwords
# are replaced. The passwords only live on this throwaway site.

set -euo pipefail

cd "$(dirname "$0")/.."

OUTPUT="${1:-${GITHUB_ENV:-.env.wp-env}}"
PORT="${WP_ENV_PORT:-8888}"
APP_PASSWORD_NAME="evals"

wp() {
	npx --no-install wp-env run cli wp "$@" 2>/dev/null
}

# user login -> role
declare -a IDENTITIES=(
	"FULL:evals-full:administrator"
	"DRAFTS_ONLY:evals-drafts-only:contributor"
)

# KEY=value line. $GITHUB_ENV keeps quotes literally; a local file is quoted
# so it can be sourced by a shell (values with spaces) and read by python-dotenv.
env_line() {
	if [[ "${OUTPUT}" == "${GITHUB_ENV:-}" ]]; then
		printf '%s=%s\n' "$1" "$2"
	else
		printf '%s="%s"\n' "$1" "$2"
	fi
}

wp rewrite structure '/%postname%/' >/dev/null

{
	env_line WP_MCP_URL "http://localhost:${PORT}/wp-json/gn-mcp/mcp"
	env_line WP_CLI "npx --no-install wp-env run cli wp"
	env_line WP_PATH ""
} >"${OUTPUT}.tmp"

for identity in "${IDENTITIES[@]}"; do
	IFS=: read -r prefix login role <<<"${identity}"

	if ! wp user get "${login}" --field=ID >/dev/null; then
		wp user create "${login}" "${login}@example.org" --role="${role}" >/dev/null
	fi
	wp user set-role "${login}" "${role}" >/dev/null

	for uuid in $(wp user application-password list "${login}" --name="${APP_PASSWORD_NAME}" --field=uuid); do
		wp user application-password delete "${login}" "${uuid}" >/dev/null
	done
	password="$(wp user application-password create "${login}" "${APP_PASSWORD_NAME}" --porcelain | tr -d '[:space:]')"

	if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
		echo "::add-mask::${password}"
	fi

	env_line "EVALS_${prefix}_USER" "${login}" >>"${OUTPUT}.tmp"
	env_line "EVALS_${prefix}_APP_PASSWORD" "${password}" >>"${OUTPUT}.tmp"
	echo "${login} (${role}): Application Password created"
done

if [[ "${OUTPUT}" == "${GITHUB_ENV:-}" ]]; then
	cat "${OUTPUT}.tmp" >>"${OUTPUT}"
	rm "${OUTPUT}.tmp"
else
	mv "${OUTPUT}.tmp" "${OUTPUT}"
	chmod 600 "${OUTPUT}"
fi
echo "Environment written to ${OUTPUT}"
