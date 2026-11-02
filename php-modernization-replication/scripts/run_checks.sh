#!/usr/bin/env bash
# Run the authors' 630 hidden PHPUnit checks on one variant (Linux port of run-test.ps1).
#   run_checks.sh HARNESS_DIR VARIANT SUBJECT_DIR RESULTS_DIR
# HARNESS_DIR is the package's UnitTest/wordPress (with its vendor/ and wordpress-base/).
set -euo pipefail
harness=$(realpath "$1"); variant=$2; subjects=$(realpath "$3"); results=$(realpath -m "$4")
out="$results/runtime/$variant"
mkdir -p "$out"
# PHP config: the system one minus ext/ftp, whose FTP_ASCII=1 differs from the harness stub's 0
# (the authors' Windows PHP did not load ftp). variables_order=EGPCS (PHP's built-in default)
# puts PHPRC/PHP_INI_SCAN_DIR into $_ENV so the harness's PHP subprocesses inherit this config.
ini="$harness/build/php-ini"
mkdir -p "$ini/conf.d"
sed 's/^variables_order *=.*/variables_order = "EGPCS"/' /etc/php/8.3/cli/php.ini > "$ini/php.ini"
for f in /etc/php/8.3/cli/conf.d/*.ini; do
    [[ $(basename "$f") == *-ftp.ini ]] || ln -sf "$f" "$ini/conf.d/"
done
export PHPRC="$ini" PHP_INI_SCAN_DIR="$ini/conf.d"
cd "$harness"
export TEST_VARIANT="$variant" SUBJECT_ROOT="$subjects" SANDBOX_ROOT="build/sandboxes/$variant"
mkdir -p "$SANDBOX_ROOT"
php vendor/bin/phpunit -c phpunit.xml \
    --log-junit "$out/junit.xml" --testdox-text "$out/testdox.txt" > "$out/stdout.txt" 2>&1 || true
tail -3 "$out/stdout.txt"
# Each check copies wordpress-base into its own sandbox (~10 GB per variant): drop them.
rm -rf -- "build/sandboxes/${variant:?}"
