from typing import List, Optional
import discord
from discord.ext import commands
from context_manager import context_manager
from config import MESSAGES
from base_commands import BaseCommandCog
from utils import validate_discord_id


class AdminCommands(BaseCommandCog):
    """Administrative commands for channel configuration and management"""
    
    @commands.hybrid_command(
        name="shootysetrole", 
        description="Set a role for the bot to ping (use role mention or ID)"
    )
    @commands.has_permissions(manage_channels=True)
    async def set_role_code(self, ctx: commands.Context, *, role_mention: str) -> None:
        """Set the role that gets pinged for sessions."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            # Validate role mention format
            if not (role_mention.startswith('<@&') and role_mention.endswith('>')):
                # Try to find role by name if not a mention
                role = discord.utils.get(ctx.guild.roles, name=role_mention)
                if role:
                    role_mention = f"<@&{role.id}>"
                else:
                    await self.send_error_embed(
                        ctx,
                        "Invalid Role",
                        "Please provide a valid role mention (@role) or role name"
                    )
                    return
            
            old_role = shooty_context.role_code
            shooty_context.role_code = role_mention
            
            # Save the context
            context_manager.save_context(channel_id)
            
            await self.send_success_embed(
                ctx,
                "Role Updated",
                f"Set this channel's ping role to {role_mention}"
            )
            
            self.logger.info(f"Changed role from {old_role} to {role_mention} in channel {channel_id}")
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need 'Manage Channels' permission to set the ping role"
            )
        except Exception as e:
            self.logger.error(f"Error in set_role_code: {e}")
            await self.send_error_embed(ctx, "Role Set Failed", "An error occurred while setting the role")
    
    @commands.hybrid_command(
        name="shootysetgame", 
        description="Set the game name for cross-server LFG features"
    )
    @commands.has_permissions(manage_channels=True)
    async def set_game_name(self, ctx: commands.Context, *, game_name: str) -> None:
        """Set the game name for cross-server Looking For Group features."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            # Validate game name
            if len(game_name.strip()) < 2:
                await self.send_error_embed(
                    ctx,
                    "Invalid Game Name",
                    "Game name must be at least 2 characters long"
                )
                return
            
            if len(game_name) > 50:
                await self.send_error_embed(
                    ctx,
                    "Game Name Too Long",
                    "Game name must be 50 characters or less"
                )
                return
            
            old_game = shooty_context.game_name
            shooty_context.game_name = game_name.upper().strip()
            shooty_context.channel = ctx.channel
            
            # Save the context
            context_manager.save_context(channel_id)
            
            await self.send_success_embed(
                ctx,
                "Game Set",
                f"Set this channel's game for LFG to **{shooty_context.game_name}**"
            )
            
            self.logger.info(f"Changed game from {old_game} to {shooty_context.game_name} in channel {channel_id}")
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need 'Manage Channels' permission to set the game name"
            )
        except Exception as e:
            self.logger.error(f"Error in set_game_name: {e}")
            await self.send_error_embed(ctx, "Game Set Failed", "An error occurred while setting the game name")
    
    @commands.hybrid_command(
        name="shootysetvoice", 
        description="Set voice channel for name bolding (use channel mention or ID)"
    )
    @commands.has_permissions(manage_channels=True)
    async def set_voice_channel(self, ctx: commands.Context, *, voice_channel_input: str = None) -> None:
        """Set the voice channel that triggers name bolding."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            if voice_channel_input is None:
                # Clear voice channel setting
                old_voice_channel_id = shooty_context.voice_channel_id
                shooty_context.voice_channel_id = None
                shooty_context.channel = ctx.channel
                
                # Save the context
                context_manager.save_context(channel_id)
                
                await self.send_success_embed(
                    ctx,
                    "Voice Channel Cleared",
                    "Names will no longer be bolded based on voice channel presence"
                )
                
                self.logger.info(f"Cleared voice channel setting (was {old_voice_channel_id}) in channel {channel_id}")
                return
            
            # Parse voice channel input (can be mention, ID, or name)
            voice_channel = None
            voice_channel_input = voice_channel_input.strip()
            
            # Try to parse as channel mention (<#123456789>)
            if voice_channel_input.startswith('<#') and voice_channel_input.endswith('>'):
                try:
                    voice_channel_id = int(voice_channel_input[2:-1])
                    voice_channel = ctx.guild.get_channel(voice_channel_id)
                except ValueError:
                    pass
            # Try to parse as channel ID
            elif voice_channel_input.isdigit():
                try:
                    voice_channel_id = int(voice_channel_input)
                    voice_channel = ctx.guild.get_channel(voice_channel_id)
                except ValueError:
                    pass
            # Try to find by name
            else:
                voice_channel = discord.utils.get(ctx.guild.voice_channels, name=voice_channel_input)
            
            if voice_channel is None:
                await self.send_error_embed(
                    ctx,
                    "Voice Channel Not Found",
                    "Please provide a valid voice channel mention (#channel), ID, or name"
                )
                return
            
            # Validate it's actually a voice channel
            if not isinstance(voice_channel, discord.VoiceChannel):
                await self.send_error_embed(
                    ctx,
                    "Invalid Channel Type",
                    "The channel must be a voice channel, not a text channel"
                )
                return
            
            # Validate voice channel is in the same guild
            if voice_channel.guild != ctx.guild:
                await self.send_error_embed(
                    ctx,
                    "Invalid Voice Channel",
                    "Voice channel must be in the same server"
                )
                return
            
            old_voice_channel_id = shooty_context.voice_channel_id
            shooty_context.voice_channel_id = voice_channel.id
            shooty_context.channel = ctx.channel
            
            # Save the context
            context_manager.save_context(channel_id)
            
            await self.send_success_embed(
                ctx,
                "Voice Channel Set",
                f"Names will now be bolded when users are in **{voice_channel.name}** 🔊"
            )
            
            self.logger.info(f"Changed voice channel from {old_voice_channel_id} to {voice_channel.id} in channel {channel_id}")
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need 'Manage Channels' permission to set the voice channel"
            )
        except Exception as e:
            self.logger.error(f"Error in set_voice_channel: {e}")
            await self.send_error_embed(ctx, "Voice Channel Set Failed", "An error occurred while setting the voice channel")
    
    @commands.hybrid_command(
        name="shootylfg",
        description="Show all players across servers playing the same game"
    )
    async def lfg(self, ctx: commands.Context) -> None:
        """Show cross-server Looking For Group information."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            if shooty_context.game_name is None:
                await self.send_error_embed(
                    ctx,
                    "No Game Set",
                    "Set this channel's game name first with `/shootysetgame`"
                )
                return
            
            # Collect users from all channels with the same game
            lobby_info = []
            total_players = 0
            
            for context in context_manager.contexts.values():
                if context.game_name == shooty_context.game_name:
                    user_list = context.get_user_list_string_with_hashtag()
                    if user_list.strip():
                        player_count = len(context.bot_soloq_user_set.union(context.bot_fullstack_user_set))
                        total_players += player_count
                        
                        # Get channel info
                        channel_info = "Unknown Channel"
                        if context.channel:
                            channel_info = f"{context.channel.guild.name} - #{context.channel.name}"
                        
                        lobby_info.append(f"**{channel_info}** ({player_count} players):\n{user_list}")
            
            if not lobby_info:
                await self.send_info_embed(
                    ctx,
                    f"No Players Found",
                    f"No players currently queued for **{shooty_context.game_name}** across all servers"
                )
                return
            
            # Create paginated response if too long
            content = "\n\n".join(lobby_info)
            
            embed = discord.Embed(
                title=f"🎮 Cross-Server LFG: {shooty_context.game_name}",
                description=f"Found **{total_players} players** across **{len(lobby_info)} channels**",
                color=0x00ff00
            )
            
            if len(content) > 1000:
                # Split into multiple fields if too long
                for i, info in enumerate(lobby_info):
                    if len(embed) + len(info) > 5900:  # Discord embed limit
                        break
                    embed.add_field(
                        name=f"Channel {i+1}",
                        value=info[:1024],  # Field value limit
                        inline=False
                    )
            else:
                embed.add_field(
                    name="Players Queued",
                    value=content,
                    inline=False
                )
            
            embed.set_footer(text="Use /shootybeacon to send messages to these players")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in lfg: {e}")
            await self.send_error_embed(ctx, "LFG Failed", "An error occurred while fetching LFG information")
    
    @commands.hybrid_command(
        name="shootybeacon",
        description="Send a cross-server message to other channels playing the same game"
    )
    @commands.cooldown(1, 60, commands.BucketType.user)  # 1 per minute per user
    async def beacon(self, ctx: commands.Context, *, message: str) -> None:
        """Send a beacon message to other channels playing the same game."""
        try:
            await self.defer_if_slash(ctx)
            
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            if shooty_context.game_name is None:
                await self.send_error_embed(
                    ctx,
                    "No Game Set",
                    "Set this channel's game name first with `/shootysetgame`"
                )
                return
            
            # Validate message
            if len(message.strip()) < 5:
                await self.send_error_embed(
                    ctx,
                    "Message Too Short",
                    "Beacon message must be at least 5 characters long"
                )
                return
            
            if len(message) > 500:
                await self.send_error_embed(
                    ctx,
                    "Message Too Long",
                    "Beacon message must be 500 characters or less"
                )
                return
            
            # Send to matching channels
            channels_pinged = []
            failed_sends = 0
            
            for context in context_manager.contexts.values():
                if (context.game_name == shooty_context.game_name and 
                    context.channel and context.channel != shooty_context.channel):
                    
                    try:
                        beacon_embed = discord.Embed(
                            title="📡 Cross-Server Beacon",
                            description=message,
                            color=0xff9500
                        )
                        beacon_embed.add_field(
                            name="From",
                            value=f"**{ctx.author.display_name}** in {shooty_context.channel.guild.name} - #{shooty_context.channel.name}",
                            inline=False
                        )
                        beacon_embed.set_footer(text=f"Game: {shooty_context.game_name}")
                        
                        await context.channel.send(
                            content=context.role_code,
                            embed=beacon_embed
                        )
                        
                        channels_pinged.append(f"**{context.channel.guild.name}** - #{context.channel.name}")
                        
                    except Exception as send_error:
                        self.logger.warning(f"Failed to send beacon to {context.channel}: {send_error}")
                        failed_sends += 1
            
            if not channels_pinged:
                await self.send_info_embed(
                    ctx,
                    "No Targets Found",
                    f"No other channels are currently set up for **{shooty_context.game_name}**"
                )
                return
            
            # Create success response
            embed = discord.Embed(
                title="📡 Beacon Sent",
                description=f"Your message was sent to **{len(channels_pinged)} channels**",
                color=0x00ff00
            )
            
            if len(channels_pinged) <= 10:  # Show all if not too many
                embed.add_field(
                    name="Sent To",
                    value="\n".join(channels_pinged),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Sent To",
                    value=f"Too many to list ({len(channels_pinged)} channels)",
                    inline=False
                )
            
            if failed_sends > 0:
                embed.add_field(
                    name="⚠️ Failed Sends",
                    value=f"{failed_sends} channels could not be reached",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
            self.logger.info(f"Beacon sent by {ctx.author} to {len(channels_pinged)} channels for {shooty_context.game_name}")
            
        except commands.CommandOnCooldown as e:
            await self.send_error_embed(
                ctx,
                "Cooldown Active",
                f"Please wait {e.retry_after:.0f} seconds before sending another beacon"
            )
        except Exception as e:
            self.logger.error(f"Error in beacon: {e}")
            await self.send_error_embed(ctx, "Beacon Failed", "An error occurred while sending the beacon")
    
    @commands.command(name="shootysync")
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx: commands.Context) -> None:
        """Sync slash commands to the current guild (Admin only)."""
        try:
            # Sync to current guild for immediate availability
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
            command_names = [cmd.name for cmd in synced]
            
            await self.send_success_embed(
                ctx,
                "Commands Synced",
                f"Synced **{len(synced)} commands** to this server\n\n**Commands:** {', '.join(command_names)}"
            )
            
            self.logger.info(f"Commands synced to {ctx.guild.name} by {ctx.author}")
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need Administrator permission to sync commands"
            )
        except Exception as e:
            self.logger.error(f"Error syncing commands: {e}")
            await self.send_error_embed(ctx, "Sync Failed", f"Error syncing commands: {str(e)}")
    
    @commands.command(name="shootysyncglobal")
    @commands.has_permissions(administrator=True)
    async def sync_global(self, ctx: commands.Context) -> None:
        """Sync slash commands globally (Admin only, takes up to 1 hour)."""
        try:
            synced = await ctx.bot.tree.sync()
            command_names = [cmd.name for cmd in synced]
            
            embed = discord.Embed(
                title="🌍 Global Sync Complete",
                description=f"Synced **{len(synced)} commands** globally",
                color=0x00ff00
            )
            embed.add_field(
                name="Commands",
                value=", ".join(command_names),
                inline=False
            )
            embed.add_field(
                name="⏰ Note",
                value="Global sync can take up to 1 hour to appear everywhere",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
            self.logger.info(f"Commands synced globally by {ctx.author}")
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need Administrator permission to sync commands globally"
            )
        except Exception as e:
            self.logger.error(f"Error syncing commands globally: {e}")
            await self.send_error_embed(ctx, "Global Sync Failed", f"Error syncing commands: {str(e)}")
    
    @commands.command(name="shootycheck")
    @commands.has_permissions(manage_guild=True)
    async def check_commands(self, ctx: commands.Context) -> None:
        """Check bot status and loaded commands (Moderator only)."""
        try:
            # Check slash commands
            slash_commands = [cmd.name for cmd in ctx.bot.tree.get_commands()]
            
            # Check cogs
            cogs = list(ctx.bot.cogs.keys())
            
            # Check specifically for Valorant commands
            valorant_cog = ctx.bot.get_cog('ValorantCommands')
            valorant_commands = []
            if valorant_cog:
                valorant_commands = [cmd.name for cmd in valorant_cog.get_commands()]
            
            # Get bot stats
            guild_count = len(ctx.bot.guilds)
            user_count = sum(guild.member_count for guild in ctx.bot.guilds)
            
            embed = discord.Embed(
                title="🔍 Bot Status Check",
                description=f"Connected to **{guild_count} servers** with **{user_count:,} total users**",
                color=0x0099ff
            )
            
            embed.add_field(
                name="Loaded Cogs",
                value=", ".join(cogs) if cogs else "None",
                inline=False
            )
            
            embed.add_field(
                name="Slash Commands",
                value=", ".join(slash_commands) if slash_commands else "None",
                inline=False
            )
            
            embed.add_field(
                name="Valorant Commands",
                value=", ".join(valorant_commands) if valorant_commands else "None found",
                inline=False
            )
            
            # Add latency info
            embed.add_field(
                name="Bot Latency",
                value=f"{ctx.bot.latency * 1000:.1f}ms",
                inline=True
            )
            
            # Add current channel settings
            shooty_context = context_manager.get_context(ctx.channel.id)
            current_game = shooty_context.game_name or "Not set"
            embed.add_field(
                name="This Channel's Game",
                value=current_game,
                inline=True
            )
            
            # Add voice channel setting
            voice_channel_name = "Not set"
            if shooty_context.voice_channel_id:
                voice_channel = ctx.guild.get_channel(shooty_context.voice_channel_id)
                voice_channel_name = voice_channel.name if voice_channel else "Invalid Channel"
            embed.add_field(
                name="Voice Channel for Bolding",
                value=voice_channel_name,
                inline=True
            )
            
            embed.set_footer(text=f"Bot ID: {ctx.bot.user.id}")
            
            await ctx.send(embed=embed)
            
        except commands.MissingPermissions:
            await self.send_error_embed(
                ctx,
                "Permission Denied",
                "You need 'Manage Server' permission to check bot status"
            )
        except Exception as e:
            self.logger.error(f"Error in check_commands: {e}")
            await self.send_error_embed(ctx, "Status Check Failed", "An error occurred while checking bot status")

async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    await bot.add_cog(AdminCommands(bot))