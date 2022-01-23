import discord
import time
import json
import requests

from discord.ext import commands
from mcstatus import MinecraftServer, MinecraftBedrockServer
from asyncio import AsyncIOScheduler

with open('config.json') as config_file:
    config = json.load(config_file)

client = commands.Bot(command_prefix=config["bot_prefix"], help_command=None, intents=discord.Intents.all())

bot_token = config['bot_token']


@client.event
async def on_ready():
    # Initialize the status of the bot in the presence
    await client.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.playing, name=config["presence_name"]))


    # Check if you have configured the discord server id
    server_id = client.get_guild(config['server_id'])
    if server_id is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: The server_id set in the configuration file is invalid!")
        return 0

    # Check if you have configured the channel id where it will write the status
    check_channel_status = server_id.get_channel(config['channel_status_id'])
    if check_channel_status is None:
        print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] ERROR: The channel_status_id set in the configuration file is invalid!")

    print("MCStats Bot: is running now on:")
    for servers in client.guilds:  
        print(servers)


async def update_servers_status():
    if config["is_maintenance_status"] == False:
        server_id = client.get_guild(config['server_id'])
        if server_id is not None:
            channel_message = server_id.get_channel(config['channel_status_id'])
            if channel_message is not None:

                txt = discord.Embed(title=config['message_title'], description=f"{config['message_description']}\n", colour=discord.Colour.orange())

                with open('data.json') as data_file:
                    data = json.load(data_file)

                with open('config.json') as server_list:
                    data_list = json.load(server_list)
                try:

                    pinger_message = await channel_message.fetch_message(int(data['pinger_message_id']))
                    checking = discord.Embed(description=config["message_checking_embed"], colour=discord.Colour.orange())
                    await pinger_message.edit(embed=checking)

                except discord.errors.NotFound:
                    checking = discord.Embed(description=config["message_checking_embed"], colour=discord.Colour.orange())
                    pinger_message = await channel_message.send(embed=checking)
                    data['pinger_message_id'] = pinger_message.id
                    new_data_file = open("data.json", "w")
                    json.dump(data, new_data_file)
                    new_data_file.close()

                for servers in data_list["servers_to_ping"]:
                    if servers["is_maintenance"] == False:
                        try:
                            if servers["is_bedrock"]:
                                check = MinecraftBedrockServer.lookup(f"{servers['server_ip']}:{servers['port']}").status().players_online
                                txt.add_field(name=servers['server_name'], value=f"🟢 ONLINE ({check} players)", inline=False)
                            else:
                                check = MinecraftServer.lookup(f"{servers['server_ip']}:{servers['port']}").status().players.online
                                txt.add_field(name=servers['server_name'], value=f"🟢 ONLINE ({check} players)", inline=False)                  
                        except:
                            txt.add_field(name=servers['server_name'], value=f"🔴 OFFLINE", inline=False)
                    else:
                        txt.add_field(name=servers['server_name'], value=f"🟠 MAINTENANCE", inline=False)

                server_list.close()

                txt.add_field(name=config["message_field"], value=config["message_field_link"], inline=False)

                txt.set_footer(text=config["message_footer"].format(date=time.strftime('%d/%m/%y'), time=time.strftime('%H:%M:%S')))

                await pinger_message.edit(embed=txt)
            else:
                print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] I could not find the servers status channel")
                return 0
        else:
            print(f"[{time.strftime('%d/%m/%y %H:%M:%S')}] I could not find the indicated discord server.")
            return 0
    else:            
        await client.change_presence(status=discord.Status.idle, activity=discord.Activity(type=discord.ActivityType.playing, name="🟠 Maintenance"))


@client.command()
async def createstatusmsg(ctx):
    if ctx.message.author.id == config['owner_id']:
        embed = discord.Embed(
            title="MCStatus Configuration.....", 
            description=f"Now copy the id of this message and put on config.json and data.json exactly on the config.json **channel_message_id** and on data.json on **pinger_message_id**.", 
            color=discord.Colour.blue())

        await ctx.send(embed=embed)
        await ctx.message.delete()

@client.command()
async def help(ctx):
    embed = discord.Embed(
        title="Commands of MCStatusBot",
        description=f"{config['prefix']}createstatusmsg - allow you to create a message where will be configured the status message.",
        color=discord.Color.dark_blue())

    embed.set_footer("Bot developed by SuperKali#8716")    
    
    await ctx.send(embed=embed)


scheduler = AsyncIOScheduler()
scheduler.add_job(update_servers_status, "interval", seconds=60)
scheduler.start()


client.run(bot_token)