#!/usr/bin/env python3
# Copyright 2022 erik.lonroth@gmail.com
# See LICENSE file for licensing details.

"""

Minecraft server charm

"""

import logging
import os
import sys
import subprocess as sp
from pathlib import Path

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError

from charmhelpers.core.host import ( adduser, add_group, symlink, chownr)
from charmhelpers.core.hookenv import ( log, config, opened_ports, open_port, close_port, status_set, resource_get )
from charmhelpers.core.host import (
    chownr,
    service_restart,
    service_running,
    service_start,
)
from charmhelpers.core.templating import render

from mcstatus import JavaServer

MINECRAFT_HOME = Path('/opt/minecraft')

logger = logging.getLogger(__name__)


class MinecraftServerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        self._stored.set_default(current_server_port=self.config['server-port'])
        
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.update_status, self._on_update_status)
        

    def _on_install(self, event):
        """
        install openjdk-8-jre-headless
        """
        try:
            self._installJava()
            MINECRAFT_HOME.mkdir(mode=0o755, parents=True, exist_ok=True)
            add_group('minecraft')
            adduser(username='minecraft', primary_group='minecraft', home_dir=str(MINECRAFT_HOME))
            chownr(str(MINECRAFT_HOME), 'minecraft', 'minecraft', chowntopdir=True)
        except Exception as e:
            logger.error("Failed to install os requirements:" + str(e))

        self.install_minecraft()

    def install_minecraft(self):
        """
        Install minecraft from resource.
        """
        self.render_eula()
        self.render_serverproperties()
        self.render_systemd()
        self.set_serverjar()
        sp.call(["systemctl", "daemon-reload"])

        self.unit.status = ActiveStatus()

    def render_eula(self):
        """ 
        Write eula.txt (This happens once at install)
        """
        with open("/opt/minecraft/eula.txt", "+w") as eula_file:
            print("eula=true", file=eula_file)
        chownr('/opt/minecraft/eula.txt','minecraft','minecraft')
        logger.info("eula.txt rendered.")

    def _on_update_status(self, _):
        """
        update-status
        """
        status = None
        
        try:
            mcs = JavaServer("127.0.0.1", int(self.config['server-port']) )
            status = mcs.status()
            gamemode = self.config['gamemode']
            if service_running('minecraft'):
                self.unit.status = ActiveStatus("{} players online ({})".format(status.players.online,gamemode))
            else:
                self.unit.status = ActiveStatus('Not running')
        except OSError:
            logger.error("Unable to connect to get server status.")
        except Exception as e:
            logger.error(e)
            sys.exit(1)

    def start_restart_server(self):
        """
        Starts and restarts the server.
        """
        sinfo = os.stat(resource_get('server-jar'))

        sp = int(self.config['server-port'])
        open_port(sp)
        
        if sinfo.st_size > 0:
            
            if not service_running('minecraft'):
                
                logger.info('Starting')

                self.unit.status = MaintenanceStatus("... starting")

                service_start('minecraft')

                self.unit.status = ActiveStatus("Ready")
            
            else:

                logger.info('Restarting.')

                self.unit.status = MaintenanceStatus("... restarting")

                service_restart('minecraft')

                self.unit.status = ActiveStatus("Ready")

                
        else:
            
            status_set('blocked', 'Need server-jar resource.')

    def _on_config_changed(self, _):
        """
        Runs when a config change to a running server has been triggered
        """   
        # Close any ports opened
        
        logger.info("server-port changed. Trying to close old ports.")
        for p in opened_ports():
            close_port(int(p.split('/')[0]))

        self.render_serverproperties()
        self.start_restart_server()

    def _installJava(self):
        """
        Install java.
        """
        self.unit.status = MaintenanceStatus("openjdk-17-jre-headless")
        os.system('apt -y install openjdk-17-jre-headless')

    def render_serverproperties(self):

        gm = self.config['gamemode']

        sp = int(self.config['server-port'])
        
        render(source='server.properties',
            target='/opt/minecraft/server.properties',
            owner='minecraft',
            group='minecraft',
            perms=0o755,
            context=self.config)
        
        logger.info("server.properties rendered.")

    def render_systemd(self):

        try:
            resource_path = self.model.resources.fetch("server-jar")
        except ModelError as e:
            self.unit.status = BlockedStatus(
                "Something went wrong when claiming resource: server-jar;"
                "run `juju debug-log` for more info'"
            ) 
            # might actually be worth it to just reraise this exception and let the charm error out;
            # depends on whether we can recover from this.
            logger.error(e)
            return
        except NameError as e:
            self.unit.status = BlockedStatus(
                "Resource 'server-jar' not found; "
                "did you forget to declare it in metadata.yaml?"
            )
            logger.error(e)
            return
        
        render(source='minecraft.service',
            target='/etc/systemd/system/minecraft.service',
        owner='root',
            perms=0o775,
        context={
                'server_jar': resource_path,
            })

        logger.info("systemd unitfile rendered.")


    def set_serverjar(self):
        """ Create and update server jar """
        resource_path = self.model.resources.fetch("server-jar")
        symlink(resource_path,'/opt/minecraft/minecraft_server.jar')


    def _on_upgrade_charm(self, _):
        """ Handle new server jar resource here """
        self.set_serverjar()



def _on_config_changed(self, event):
    # Get the path to the file resource named 'my-resource'
    try:
        resource_path = self.model.resources.fetch("my-resource")
    except ModelError as e:
        self.unit.status = BlockedStatus(
            "Something went wrong when claiming resource 'my-resource; "
            "run `juju debug-log` for more info'"
        ) 
       # might actually be worth it to just reraise this exception and let the charm error out;
       # depends on whether we can recover from this.
        logger.error(e)
        return
    except NameError as e:
        self.unit.status = BlockedStatus(
            "Resource 'my-resource' not found; "
            "did you forget to declare it in metadata.yaml?"
        )
        logger.error(e)
        return

    # Open the file and read it
    with open(resource_path, "r") as f:
        content = f.read()

if __name__ == "__main__":
    main(MinecraftServerCharm)
