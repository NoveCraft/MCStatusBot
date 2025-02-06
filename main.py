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
def process_env_vars(config):
    """
    Reemplaza variables de entorno en el diccionario de configuración.
    Por ejemplo, si un valor es "${BOT_TOKEN}", se reemplaza por el valor real.
    """
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            env_value = os.environ.get(env_var)
            if env_value is None:
                raise ValueError(f"La variable de entorno {env_var} no está definida.")
            config[key] = env_value
    return config

# Cargar configuración desde config.json y procesar variables de entorno
with open('config.json') as config_file:
    config = json.load(config_file)
config = process_env_vars(config)

# -------------------------------
# Se instancia el bot; aunque no usemos comandos, se requiere para Nextcord.
client = commands.Bot(
    command_prefix=config["bot_prefix"],
    help_command=None,
    intents=nextcord.Intents.all()
)

bot_token = config['bot_token']
count_all_servers = {}
scheduler = AsyncIOScheduler()  # Se iniciará en on_ready()

DATA_FILE = "data.json"  # Archivo donde se almacena el ID del mensaje de estado

# -------------------------------
# Servidor web simple (útil para mantener la aplicación activa)
async def handle_root(request):
    return web.Response(text="¡Hola! La aplicación está corriendo.")

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_root)
    
    # Usa el puerto definido en la variable de entorno PORT, o 8080 por defecto
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[DEBUG] Servidor web corriendo en el puerto {port}")

# -------------------------------
async def ensure_status_message(channel):
    """
    Verifica si existe un mensaje de estado (almacenado en DATA_FILE).
    Si no existe o si el ID almacenado es 0, lo crea automáticamente en el canal indicado.
    Retorna el ID del mensaje.
    """
    data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print("[DEBUG] data.json está corrupto o vacío. Se reiniciará el contenido.")
            data = {}

    # Si ya existe un ID y no es 0, lo usamos
    if "pinger_message_id" in data and data["pinger_message_id"] != 0:
        print(f"[DEBUG] Mensaje de estado ya existe: ID {data['pinger_message_id']}")
        return data["pinger_message_id"]
    else:
        print("[DEBUG] No se encontró mensaje de estado válido, creándolo...")
        embed = nextcord.Embed(
            title="MCStatusBot Configured 🎉",
            description="This message will be updated automatically with the server status.",
            color=nextcord.Colour.blue()
        )
        try:
            message = await channel.send(embed=embed)
            data["pinger_message_id"] = message.id
            with open(DATA_FILE, "w") as f:
                json.dump(data, f)
            print(f"[DEBUG] Mensaje de estado creado con ID {message.id}")
            return message.id
        except Exception as e:
            print(f"[ERROR] Error al crear el mensaje de estado: {e}")
            return None

# -------------------------------
@client.event
async def on_ready():
    global scheduler

    init(autoreset=True)
    print("[DEBUG] on_ready iniciado.")

    # Iniciar el servidor web en segundo plano
    client.loop.create_task(start_webserver())

    # Cambiar la presencia del bot (opcional)
    await client.change_presence(
        status=nextcord.Status.online,
        activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="...loading")
    )

    # Verificar guild y canal según la configuración
    guild = client.get_guild(int(config['server_id']))
    if guild is None:
        print(f"[ERROR] El server_id {config['server_id']} en config.json es inválido.")
        return

    channel = guild.get_channel(int(config['channel_status_id']))
    if channel is None:
        print(f"[ERROR] El channel_status_id {config['channel_status_id']} en config.json es inválido.")
        return

    print(f"[DEBUG] Guild y canal encontrados: {guild.name} / {channel.name}")

    # Asegurarse de que exista el mensaje de estado; si no, se crea automáticamente.
    message_id = await ensure_status_message(channel)
    if not message_id:
        print("[ERROR] No se pudo crear o recuperar el mensaje de estado.")
        return

    # Iniciar el scheduler para actualizar el mensaje periódicamente
    if not scheduler.running:
        scheduler.add_job(update_servers_status, "interval", seconds=config["refresh_time"])
        scheduler.start()
        print("[DEBUG] Scheduler iniciado.")

    print(Style.NORMAL + Fore.LIGHTMAGENTA_EX + "╔═══════════════════╗")
    print(Style.NORMAL + Fore.GREEN + "Nombre: " + Fore.RED + "MCStatusBot")
    print(Style.NORMAL + Fore.GREEN + "Versión: " + Fore.RED + "v1.3")
    print(Style.NORMAL + Fore.GREEN + "Tiempo de actualización: " + Fore.RED + f"{config['refresh_time']} segundos")
    print(Style.NORMAL + Fore.GREEN + "Estado del Bot: " + Fore.RED + "Online")
    print(Style.NORMAL + Fore.GREEN + "Soporte: " + Fore.RED + "https://discord.superkali.me")
    print(Style.NORMAL + Fore.LIGHTMAGENTA_EX + "╚═══════════════════╝")

# -------------------------------
async def update_servers_status():
    """
    Función que se ejecuta periódicamente para actualizar el mensaje de estado.
    """
    if not config["is_maintenance_status"]:
        guild = client.get_guild(int(config['server_id']))
        if guild:
            channel = guild.get_channel(int(config['channel_status_id']))
            if channel:
                try:
                    with open(DATA_FILE, "r") as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"[ERROR] No se pudo leer {DATA_FILE}: {e}")
                    return

                if "pinger_message_id" not in data or data["pinger_message_id"] == 0:
                    print("[DEBUG] El mensaje de estado no está configurado o es inválido. Se creará nuevamente.")
                    message_id = await ensure_status_message(channel)
                    if not message_id:
                        return
                else:
                    message_id = data["pinger_message_id"]

                txt = nextcord.Embed(
                    title=config['message_title'],
                    description=f"{config['message_description']}\n",
                    colour=nextcord.Colour.orange()
                )

                # Cargar la lista de servidores a pinguear desde config.json
                with open('config.json') as server_list:
                    data_list = json.load(server_list)

                try:
                    pinger_message = await channel.fetch_message(int(message_id))
                    # Mostrar un embed "checking" mientras se actualiza el estado
                    checking = nextcord.Embed(
                        description=config["message_checking_embed"],
                        colour=nextcord.Colour.orange()
                    )
                    await pinger_message.edit(embed=checking)
                except nextcord.errors.NotFound:
                    print("[DEBUG] El mensaje de estado no se encontró. Creándolo nuevamente...")
                    message_id = await ensure_status_message(channel)
                    if not message_id:
                        return
                    pinger_message = await channel.fetch_message(int(message_id))
                except Exception as e:
                    print(f"[ERROR] Error al obtener el mensaje de estado: {e}")
                    return

                # Actualizar el embed con el estado de cada servidor
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
                        except Exception as e:
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

                try:
                    await pinger_message.edit(embed=txt)
                    print("[DEBUG] Mensaje de estado actualizado correctamente.")
                except Exception as e:
                    print(f"[ERROR] No se pudo actualizar el mensaje: {e}")

                await send_console_status()
                await update_presence_status()
            else:
                print(f"[ERROR] No se encontró el canal de estado.")
        else:
            print(f"[ERROR] No se encontró el servidor de Discord configurado.")
    else:
        await client.change_presence(
            status=nextcord.Status.idle,
            activity=nextcord.Activity(type=nextcord.ActivityType.playing, name="🟠 Mantenimiento")
        )

# -------------------------------
async def update_presence_status():
    """
    Actualiza la presencia del bot mostrando el total de jugadores en línea.
    """
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
    """
    Imprime en consola el estado actual de los servidores.
    """
    online_count = sum(1 for info in count_all_servers.values() if info.get("status", False))
    offline_count = sum(1 for info in count_all_servers.values() if not info.get("status", False))
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + "Estado actual de los servidores:")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{online_count} servidores en línea")
    print(Style.NORMAL + Fore.RED + "[MCStatusBot] " + Fore.CYAN + f"{offline_count} servidores fuera de línea")

# -------------------------------
client.run(bot_token)
