import asyncio
import nextcord
import time
import json
import os

from nextcord.ext import commands
from mcstatus import JavaServer, BedrockServer
from colorama import init, Fore, Style
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Cargar configuración desde JSON
with open('config.json') as config_file:
    config = json.load(config_file)

client = commands.Bot(command_prefix=config["bot_prefix"], help_command=None, intents=nextcord.Intents.all())

bot_token = config['bot_token']
count_all_servers = {}
scheduler = AsyncIOScheduler()  # Se define pero se inicia dentro de on_ready()


@client.event
async def on_ready():
    global scheduler

    # Inicializar colores para la consola
    init(autoreset=True)

    # Configurar presencia del bot
    await client.change_presence(status=nextcord.Status.online, activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="...loading"))

    # Validar configuraciones
    server_id = client.get_guild(int(config['server_id']))
    if server_id is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: El server_id en config.json es inválido.")
        return

    check_channel_status = server_id.get_channel(int(config['channel_status_id']))
    if check_channel_status is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: El channel_status_id en config.json es inválido.")

    owner_id = client.get_user(int(config['owner_id']))
    if owner_id is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: El owner_id en config.json es inválido.")

    # Cargar Cogs (módulos adicionales)
    for i in os.listdir('./cogs'):
        if i.endswith('.py'):
            client.load_extension(f'cogs.{i[:-3]}')

    # Iniciar el scheduler solo si aún no está corriendo
    if not scheduler.running:
        scheduler.add_job(update_servers_status, "interval", seconds=config["refresh_time"])
        scheduler.start()

    print(Style.NORMAL + Fore.LIGHTMAGENTA_EX + "╔═══════════════════╗")
    print(Style.NORMAL + Fore.GREEN + "Nombre: " + Fore.RED + "MCStatusBot")
    print(Style.NORMAL + Fore.GREEN + "Versión: " + Fore.RED + "v1.3")
    print(Style.NORMAL + Fore.GREEN + "Tiempo de actualización: " + Fore.RED + f"{config['refresh_time']} segundos")
    print(Style.NORMAL + Fore.GREEN + "Estado del Bot: " + Fore.RED + "Online")
    print(Style.NORMAL + Fore.GREEN + "Soporte: " + Fore.RED + "https://discord.superkali.me")
    print(Style.NORMAL + Fore.LIGHTMAGENTA_EX + "╚═══════════════════╝")


async def update_servers_status():
    if not config["is_maintenance_status"]:
        server_id = client.get_guild(int(config['server_id']))
        if server_id:
            channel_message = server_id.get_channel(int(config['channel_status_id']))
            if channel_message:

                txt = nextcord.Embed(title=config['message_title'], description=f"{config['message_description']}\n", colour=nextcord.Colour.orange())

                with open('data.json') as data_file:
                    data = json.load(data_file)

                with open('config.json') as server_list:
                    data_list = json.load(server_list)

                try:
                    pinger_message = await channel_message.fetch_message(int(data['pinger_message_id']))
                    checking = nextcord.Embed(description=config["message_checking_embed"], colour=nextcord.Colour.orange())
                    await pinger_message.edit(embed=checking)

                except nextcord.errors.NotFound:
                    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"El bot no está configurado. Usa {config['bot_prefix']}createstatusmsg en el canal de texto.")
                    return

                for servers in data_list["servers_to_ping"]:
                    if not servers["is_maintenance"]:
                        try:
                            if servers["is_bedrock"]:
                                check = BedrockServer.lookup(f"{servers['server_ip']}:{servers['port']}").status().players.online
                            else:
                                check = JavaServer.lookup(f"{servers['server_ip']}:{servers['port']}").status().players.online
                            
                            txt.add_field(name=servers['server_name'], value=f"🟢 ONLINE ({check} jugadores)", inline=False)
                            count_all_servers[servers['server_name']] = {"online": check, "count_on_presence": servers["count_on_presence"], "status": True}

                        except:
                            txt.add_field(name=servers['server_name'], value="🔴 OFFLINE", inline=False)
                            count_all_servers[servers['server_name']] = {"online": 0, "count_on_presence": servers["count_on_presence"], "status": False}
                    else:
                        txt.add_field(name=servers['server_name'], value="🟠 MANTENIMIENTO", inline=False)

                if config["message_field"] and config["message_field_link"]:
                    txt.add_field(name=config["message_field"], value=config["message_field_link"], inline=False)

                txt.set_footer(text=config["message_footer"].format(date=time.strftime('%d/%m/%y'), time=time.strftime('%H:%M:%S')))

                await pinger_message.edit(embed=txt)
                await send_console_status()
                await update_presence_status()
            else:
                print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] No se encontró el canal de estado de servidores.")
        else:
            print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] No se encontró el servidor de Discord configurado.")
    else:
        await client.change_presence(status=nextcord.Status.idle, activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="🟠 Mantenimiento"))


async def update_presence_status():
    servers = count_all_servers.values()
    total_players = sum(int(value.get('online', 0)) for value in servers if value.get("count_on_presence", False))

    await client.change_presence(status=nextcord.Status.online, activity=nextcord.Activity(type=nextcord.ActivityType.playing, name=config["presence_name"].format(players=total_players)))
    count_all_servers.clear()


async def send_console_status():
    servers = count_all_servers.values()
    online_count = sum(1 for value in servers if value.get("status", False))
    offline_count = sum(1 for value in servers if not value.get("status", False))

    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + "Estado actual de los servidores:")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{online_count} servidores en línea")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{offline_count} servidores fuera de línea")


client.run(bot_token)
