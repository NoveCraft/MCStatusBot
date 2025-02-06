import nextcord
import json
from nextcord.ext import commands

class Commands(commands.Cog):
    def __init__(self, client):
        self.client = client
        with open('config.json') as f:
            self.config = json.load(f)
    
    @commands.command()
    async def createstatusmsg(self, ctx):
        # Intentar cargar data.json; si no existe, se crea un diccionario vacío
        try:
            with open('data.json', 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        
        # Verificar si el comando ya fue usado (es decir, ya existe 'pinger_message_id')
        if "pinger_message_id" in data:
            await ctx.send("Este comando ya se ha usado y solo puede usarse una vez.")
            return

        embed = nextcord.Embed(
            title="MCStatusBot Configured 🎉",
            description="This message will be updated with the status message automatically.",
            color=nextcord.Colour.blue()
        )

        message = await ctx.send(embed=embed)
        await ctx.message.delete()

        data['pinger_message_id'] = message.id
        with open("data.json", "w") as f:
            json.dump(data, f)
        await ctx.send("Mensaje de estado configurado correctamente. Este comando no se podrá volver a usar.")

    @commands.command()
    async def help(self, ctx):
        embed = nextcord.Embed(
            title="Commands of MCStatusBot",
            description=f"{self.config['bot_prefix']}createstatusmsg - Crea el mensaje donde se actualizará el estado automáticamente.",
            color=nextcord.Colour.dark_blue()
        )
        embed.set_footer(text="Bot developed by SuperKali#8716")
        await ctx.send(embed=embed)

async def setup(client):
    client.add_cog(Commands(client))
