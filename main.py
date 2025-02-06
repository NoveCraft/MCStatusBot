import asyncio
import nextcord
import time
import json
import os

from nextcord.ext import commands
from mcstatus import JavaServer, BedrockServer
from colorama import init, Fore, Style
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# -------------------------------
# Función para procesar variables de entorno en la configuración
def process_env_vars(config):
    for key, value in config.items():
        if isinstance(value, str):
            # Si el valor tiene el formato ${VARIABLE}, se reemplaza por la variable de entorno
            if value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                env_value = os.environ.get(env_var)
                if env_value is None:
                    raise ValueError(f"La variable de entorno {env_var} no está definida.")
                config[key] = env_value
    return config

# Cargar configuración desde JSON y procesar variables de entorno
with open('config.json') as config_file:
    config = json.load(config_file)
config = process_env_vars(config)

# -------------------------------
client = commands.Bot(
    command_prefix=config["bot_prefix"],
    help_command=None,
    intents=nextcord.Intents.all()
)

bot_token = config['bot_token']
count_all_servers = {}
scheduler = AsyncIOScheduler()  # Se definirá e iniciará en on_ready()

# Bandera global para controlar el uso único del comando
status_created = False

# -------------------------------
# Función del servidor web simple
async def handle_root(request):
    return web.Response(text="¡Hola! La aplicación está corriendo.")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_root)
    
    # Obtiene el puerto de la variable de entorno "PORT" (usado por Render), o usa 8080 por defecto.
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Servidor web corriendo en el puerto {port}")

# -------------------------------
@client.event
async def on_ready():
    global scheduler

    # Inicializar colores para la consola
    init(autoreset=True)

    # Iniciar el servidor web en segundo plano
    client.loop.create_task(start_webserver())

    # Configurar presencia del bot
    await client.change_presence(
        status=nextcord.Status.online,
        activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="...loading")
    )

    # Validar configuraciones
    server = client.get_guild(int(config['server_id']))
    if server is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: El server_id en config.json es inválido.")
        return

    check_channel_status = server.get_channel(int(config['channel_status_id']))
    if check_channel_status is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: El channel_status_id en config.json es inválido.")

    # Cargar Cogs (módulos adicionales)
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            client.load_extension(f'cogs.{filename[:-3]}')

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

# -------------------------------
# Comando para crear el mensaje de estado (solo se puede usar una vez)
@client.command(name="createstatusmsg")
async def create_status_msg(ctx):
    global status_created
    if status_created:
        await ctx.send("Este comando ya se ha usado y solo puede usarse una vez.")
        return

    # Enviar un mensaje inicial que luego actualizará el scheduler
    message = await ctx.send("Mensaje de estado creado. Este mensaje se actualizará automáticamente.")
    
    # Guardar el ID del mensaje en data.json para que update_servers_status lo use
    try:
        with open('data.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    data['pinger_message_id'] = message.id
    with open('data.json', 'w') as f:
        json.dump(data, f)

    status_created = True
    await ctx.send("Mensaje de estado configurado correctamente. Este comando no se podrá volver a usar.")

# -------------------------------
async def update_servers_status():
    if not config["is_maintenance_status"]:
        server = client.get_guild(int(config['server_id']))
        if server:
            channel_message = server.get_channel(int(config['channel_status_id']))
            if channel_message:
                txt = nextcord.Embed(
                    title=config['message_title'],
                    description=f"{config['message_description']}\n",
                    colour=nextcord.Colour.orange()
                )

                with open('data.json') as data_file:
                    data = json.load(data_file)

                # Se vuelve a cargar config.json para obtener la lista de servidores a pinguear
                with open('config.json') as server_list:
                    data_list = json.load(server_list)
                try:
                    pinger_message = await channel_message.fetch_message(int(data['pinger_message_id']))
                    checking = nextcord.Embed(
                        description=config["message_checking_embed"],
                        colour=nextcord.Colour.orange()
                    )
                    await pinger_message.edit(embed=checking)
                except nextcord.errors.NotFound:
                    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN +
                          f"El mensaje de estado no está configurado. Usa {config['bot_prefix']}createstatusmsg en el canal de texto.")
                    return

                for server_info in data_list["servers_to_ping"]:
                    if not server_info["is_maintenance"]:
                        try:
                            if server_info["is_bedrock"]:
                                check = BedrockServer.lookup(
                                    f"{server_info['server_ip']}:{server_info['port']}"
                                ).status().players.online
                            else:
                                check = JavaServer.lookup(
                                    f"{server_info['server_ip']}:{server_info['port']}"
                                ).status().players.online
                            txt.add_field(
                                name=server_info['server_name'],
                                value=f"🟢 ONLINE ({check} jugadores)",
                                inline=False
                            )
                            count_all_servers[server_info['server_name']] = {
                                "online": check,
                                "count_on_presence": server_info["count_on_presence"],
                                "status": True
                            }
                        except Exception:
                            txt.add_field(name=server_info['server_name'], value="🔴 OFFLINE", inline=False)
                            count_all_servers[server_info['server_name']] = {
                                "online": 0,
                                "count_on_presence": server_info["count_on_presence"],
                                "status": False
                            }
                    else:
                        txt.add_field(name=server_info['server_name'], value="🟠 MANTENIMIENTO", inline=False)

                if config["message_field"] and config["message_field_link"]:
                    txt.add_field(name=config["message_field"], value=config["message_field_link"], inline=False)

                txt.set_footer(text=config["message_footer"].format(
                    date=time.strftime('%d/%m/%y'),
                    time=time.strftime('%H:%M:%S')
                ))

                await pinger_message.edit(embed=txt)
                await send_console_status()
                await update_presence_status()
            else:
                print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] No se encontró el canal de estado de servidores.")
        else:
            print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] No se encontró el servidor de Discord configurado.")
    else:
        await client.change_presence(
            status=nextcord.Status.idle,
            activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="🟠 Mantenimiento")
        )

# -------------------------------
async def update_presence_status():
    total_players = sum(
        int(info.get('online', 0))
        for info in count_all_servers.values()
        if info.get("count_on_presence", False)
    )
    await client.change_presence(
        status=nextcord.Status.online,
        activity=nextcord.Activity(
            type=nextcord.ActivityType.playing,
            name=config["presence_name"].format(players=total_players)
        )
    )
    count_all_servers.clear()

# -------------------------------
async def send_console_status():
    online_count = sum(1 for info in count_all_servers.values() if info.get("status", False))
    offline_count = sum(1 for info in count_all_servers.values() if not info.get("status", False))

    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + "Estado actual de los servidores:")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{online_count} servidores en línea")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{offline_count} servidores fuera de línea")

# -------------------------------
client.run(bot_token)
