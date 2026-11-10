"""Create the initial administrator, with a password entered without echo."""
import argparse
from getpass import getpass

from src.repositories.postgres_store import PostgresStore
from .authentication import AuthenticationService, AuthError
from .encryption import EncryptionService, DEFAULT_KEY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['bootstrap','storage-key'])
    parser.add_argument('--username', default='admin')
    parser.add_argument('--db-schema', default='smartcare')
    args = parser.parse_args()
    if args.command == 'storage-key':
        try:
            EncryptionService.create_key()
        except FileExistsError:
            print('La clé existe déjà : conservée sans modification.')
        else:
            print(f'Clé créée dans {DEFAULT_KEY}. Conservez une sauvegarde privée avec celle de la base.')
        return
    password = getpass('Mot de passe administrateur (12–128 caractères) : ')
    if password != getpass('Confirmer le mot de passe : '):
        parser.error('Les mots de passe diffèrent.')
    with PostgresStore(schema=args.db_schema):
        pass
    service = AuthenticationService(lambda: PostgresStore(schema=args.db_schema, initialize=False))
    try:
        service.create_user(args.username, password, 'ADMIN', bootstrap=True)
    except AuthError as error:
        parser.error(error.message)
    print('Administrateur créé. Vous pouvez vous connecter au dashboard.')


if __name__ == '__main__':
    main()
