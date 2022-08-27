# charm-minecraft-server
This is a juju charm which sets up a Minecraft server and allows you to manage it over time.

Its developed with the ops framework for juju.

See full documentation: [minecraft-server/README.md](minecraft-server/README.md)


## Building/Developing the charm

    cd minecraft-server
    charmcraft pack

## Releasing

    charmcraft upload minecraft-server_ubuntu-20.04-amd64.charm --name erik-lonroth-minecraft-server
