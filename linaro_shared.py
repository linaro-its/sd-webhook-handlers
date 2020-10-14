"""
Some functions shared across the handlers that are too Linaro-specific
to be included in sd-webhook-framework.
"""

import os
import pwd
import stat
import subprocess
import traceback

import shared.shared_sd as shared_sd


def pem_path():
    """ Work out where the PEM file is located. """
    script_directory = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(script_directory, "it-support-bot.pem")


def trigger_google_sync(level=""):
    """Connect to Linaro Login over SSH to trigger GCDS."""
    if not check_pem():
        return
    try:
        process = subprocess.Popen([
            'ssh',
            '-T',
            '-i%s' % pem_path(),
            'it-support-bot@login-us-east-1.linaro.org',
            level], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, stderrdata = process.communicate()
        if stdoutdata == "" and stderrdata == "":
            shared_sd.post_comment(
                "Synchronisation to Google triggered. It may take up to 15 "
                "minutes before the changes are visible on Google.", True)
        else:
            if stdoutdata != "":
                shared_sd.post_comment(
                    "GCDS stdout = '%s'" %
                    stdoutdata, False)
            if stderrdata != "":
                shared_sd.post_comment(
                    "GCDS stderr = '%s'" %
                    stderrdata, False)
    # pylint: disable=broad-except
    except Exception as _:
        shared_sd.post_comment(
            "Got error while triggering GCDS: %s" % traceback.format_exc(),
            False)


def check_pem():
    """
    Make sure that the pem file is owned correctly and has the correct file
    permissions.
    """
    result = os.stat(pem_path())
    if stat.S_IMODE(result.st_mode) != 384:  # 0600 octal
        shared_sd.post_comment(
            "BOT PEM file has incorrect permissions.", False)
        return False
    if pwd.getpwuid(result.st_uid).pw_name != "www-data":
        shared_sd.post_comment(
            "BOT PEM file has incorrect owner.", False)
        return False
    return True


def cleanup_if_markdown(email_address):
    """
    If the email address has been copied/pasted from elsewhere, it can sometimes
    get turned into a markdown version, e.g.:

    [<email>|mailto:<email>]

    and it is tricky for users to avoid that so we clean it up here.
    """
    if (email_address is None or
            email_address == "" or
            email_address[0] != '[' or
            email_address[-1] != ']' or
            '|' not in email_address):
        return email_address

    parts = email_address.split('|')
    if len(parts) != 2:
        return email_address
    # Make sure the second part is a mailto:
    part2 = parts[1]
    if (len(part2) <= len("mailto:") or
            part2[:len("mailto:")] != "mailto:"):
        return email_address

    # Remove the trailing ] and return the email address
    return part2[len("mailto:"):-1]
