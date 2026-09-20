# Install as config.sh beside the HOST-OWNED receive.sh. Owner-only permissions.
# All paths must be absolute. Keep live paths and hostnames out of this repository.
DOCKER=/usr/bin/docker
CHECKOUT=/srv/frontporch
STATE_DIR=/srv/frontporch-deploy/state
BACKUP_DIR=/srv/frontporch-backups
SSH_DIR=/root/.ssh
PROJECT=frontporch
REPOSITORY=porchlab/frontporch
ORIGIN=git@github.com:porchlab/frontporch.git
PYTHON_IMAGE=python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
GIT_IMAGE=alpine/git@sha256:8d6ede0b29c666ac111c732468c4d758c1c08f054f211dd98f15d421a6ffab40
