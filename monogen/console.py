#!/usr/bin/env python3

import sys

from argparse import ArgumentParser
from re import match
from csv import DictWriter
from pathlib import Path

try:
    from monocle.utils import generate_device_info
    GENERATE_DEVICE = True
except ImportError:
    GENERATE_DEVICE = False

from .ptcexceptions import *
from .gmailv import *
from .url import *
from .accountcreator import random_account


def parse_arguments():
    """Parse the command line arguments for the console commands.
    Args:
      args (List[str]): List of string arguments to be parsed.
    Returns:
      Namespace: Namespace with the parsed arguments.
    """
    parser = ArgumentParser(
        description='Pokemon Trainer Club Account Creator'
    )
    parser.add_argument(
        '-u', '--username', type=str, default=None,
        help='Username for the new account (defaults to random string).'
    )
    parser.add_argument(
        '-p', '--password', type=str, default=None,
        help='Password for the new account (defaults to random string).'
    )
    parser.add_argument(
        '-e', '--email', type=str,
        help='Email for the new account.'
    )
    parser.add_argument(
        '-n', '--no-plusmail', dest='plusmail', action='store_false',
        help='Do not append the username to your email after a plus sign.'
    )
    parser.add_argument(
        '-av', '--autoverify', dest='autoverify', action='store_true',
        help='Append the argument -av True if you want to use autoverify with +mail.'
    )
    parser.add_argument(
        '-b', '--birthday', type=str, default=None,
        help='Birthday for the new account. Must be YYYY-MM-DD. (defaults to a random birthday).'
    )
    parser.add_argument(
        '-c','--count', type=int, default=1,
        help='Number of accounts to generate.'
    )
    parser.add_argument(
        '-r','--recaptcha', type=str, default=None,
        help='Your 2captcha key from settings'
    )
    parser.add_argument(
        '-gm', '--googlemail', type=str, default=None,
        help='This is the mail for the google account when auto verify is activated (Only required if plus mail is different from google mail)'
    )
    parser.add_argument(
        '-gp','--googlepass', type=str, default=None,
        help='This is the password for the google account and is require to activate auto verify when using the plus mail'
    )    
    parser.add_argument(
        '-f','--csvfile', type=str, default='accounts.csv',
        help='This is the location you want to save your accounts CSV to.'
    )
    parser.add_argument(
        '-it','--inputtext', type=str, default=None,
        help='This is the location you want to read usernames in the format user:pass'
    ) 
    parser.add_argument(
        '-sn','--startnum', type=int, default=None,
        help='If you specify both -u and -c, it will append a number to the end. This allows you to choose where to start from'
    )
    parser.add_argument(
        '-ct','--captchatimeout', type=int, default=500,
        help='Allows you to set the time to timeout captcha and forget that account (and forgeit $0.003).'
    )
    parser.add_argument(
        '-q', '--queue', dest='queue', action='store_true',
        help='Automatically add account to Monocle queue.'
    )
    parser.add_argument(
        '-m', '--monocle-dir', type=str, default=None,
        help='Monocle location, defaults to current directory.'
    )

    return parser.parse_args()

def _verify_autoverify_email(settings):
    if (settings['args'].googlepass is not None and settings['args'].plusmail is None and settings['args'].googlemail is None):
        raise PTCInvalidEmailException("You have to specify an email (--email or -e) or a google email (--googlemail or -gm) to use autoverification.")

def _verify_plusmail_format(settings):
    if (settings['args'].plusmail and not match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", settings['args'].email)):
        raise PTCInvalidEmailException("Invalid email format to use with plusmail.")

def _verify_twocaptcha_balance(settings):
    if (settings['args'].recaptcha is not None and settings['balance'] == 'ERROR_KEY_DOES_NOT_EXIST'):
        raise PTCTwocaptchaException("2captcha key does not exist.")
    if (settings['args'].recaptcha is not None and float(settings['balance']) < float(settings['args'].count)*0.003):
        raise PTCTwocaptchaException("It does not seem like you have enough balance for this run. Lower the count or increase your balance.")

def _verify_settings(settings):
    verifications=[_verify_autoverify_email, _verify_plusmail_format, _verify_twocaptcha_balance]
    for verification in verifications:
        try:
            verification(settings)
        except PTCException as e:
            print(e.message)
            print("Terminating.")
            sys.exit()
    return True

def entry():
    """Main entry point for the package console commands"""
    args = parse_arguments()

    global GENERATE_DEVICE

    if not GENERATE_DEVICE:
        if args.monocle_dir:
            sys.path.append(args.monocle_dir)
        else:
            sys.path.append('.')
        try:
            from monocle.utils import generate_device_info
            GENERATE_DEVICE = True
        except ImportError:
            GENERATE_DEVICE = False

    if args.queue:
        if not GENERATE_DEVICE:
            raise ImportError('Could not find Monocle, are you in the right folder?')
        from .monoqueue import add_to_queue

    captchabal = None
    if args.recaptcha is not None:
        captchabal = "Failed"
        while(captchabal == "Failed"):
            captchabal = openurl("http://2captcha.com/res.php?key=" + args.recaptcha + "&action=getbalance")
        print(("Your 2captcha balance is: " + captchabal))
        print(("This run will cost you approximately: " + str(float(args.count)*0.003)))

    username = args.username    
    
    if args.inputtext is not None:
        print(("Reading accounts from: " + args.inputtext))
        lines = [line.rstrip('\n') for line in open(args.inputtext, "r")]
        args.count = len(lines)

    output = Path(args.csvfile)
    write_header = not output.exists()
    newline = False
    if not write_header:
        with output.open('r') as f:
            newline = f.read()[-1] != '\n'

    if _verify_settings({'args':args, 'balance':captchabal}):
        for x in range(args.count):
            print("Making account #{}".format(x + 1))
            if args.username is not None and args.count != 1 and args.inputtext is None:
                if args.startnum is None:
                    username = '{}{}'.format(args.username, x + 1)
                else:
                    username = '{}{}'.format(args.username, args.startnum + x)
            if args.inputtext is not None:
                username = ((lines[x]).split(":"))[0]
                args.password = ((lines[x]).split(":"))[1]
            error_msg = None
            try:
                try:
                    account_info = random_account(args.email, username, args.password, args.birthday, args.plusmail, args.recaptcha, args.captchatimeout)
                    
                    print('  Username:  {}'.format(account_info["username"]))
                    print('  Password:  {}'.format(account_info["password"]))
                    print('  Email   :  {}'.format(account_info["email"]))

                    # Verify email
                    if (args.googlepass is not None):
                        if (args.googlemail is not None):
                            email_verify(args.googlemail, args.googlepass)
                        else:
                            email_verify(args.email, args.googlepass)

                    if GENERATE_DEVICE:
                        account_info = generate_device_info(account_info)

                    # Append usernames
                    with output.open('a') as csvfile:
                        fieldnames = ('username', 'password', 'provider', 'model', 'iOS', 'id')
                        writer = DictWriter(csvfile, fieldnames, delimiter=',', extrasaction='ignore')

                        if write_header:
                            writer.writeheader()
                            write_header = False
                        elif newline:
                            csvfile.write('\r\n')
                            newline = False

                        writer.writerow(account_info)
                    if args.queue:
                        add_to_queue(account_info)
                # Handle account creation failure exceptions
                except PTCInvalidPasswordException as err:
                    error_msg = 'Invalid password: {}'.format(err)
                except (PTCInvalidEmailException, PTCInvalidNameException) as err:
                    error_msg = 'Failed to create account! {}'.format(err)
                except PTCException as err:
                    error_msg = 'Failed to create account! General error:  {}'.format(err)
            except Exception:
                import traceback
                error_msg = "Generic Exception: " + traceback.format_exc()
            if error_msg:
                if args.count == 1:
                    sys.exit(error_msg)
                print(error_msg)
