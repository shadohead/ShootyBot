"""Base command classes for ShootyBot."""

import logging
from typing import Optional, List, Dict, Any, Union
import discord
from discord.ext import commands
from discord import app_commands

from utils import log_error, safe_embed_field
from config import MESSAGES


class BaseCommandCog(commands.Cog):
    """Base class for all command cogs with common functionality."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        self.logger.info(f"Loading {self.__class__.__name__}")
    
    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        self.logger.info(f"Unloading {self.__class__.__name__}")
    
    async def cog_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handle errors for commands in this cog."""
        # Let specific errors bubble up to global handler
        if isinstance(error, (commands.CommandNotFound, commands.MissingPermissions,
                            commands.MissingRequiredArgument, commands.BadArgument)):
            raise error
        
        # Log unexpected errors
        command_name = ctx.command.qualified_name if ctx.command else 'Unknown'
        log_error(f"in {self.__class__.__name__}.{command_name}", error)
        
        # Send user-friendly error message
        await self.send_error_embed(ctx, "An unexpected error occurred", str(error))
    
    async def send_embed(self, ctx: Union[commands.Context, discord.Interaction],
                        title: str, description: str = None, color: int = 0x00ff00,
                        fields: List[Dict[str, Any]] = None, thumbnail: str = None,
                        footer: str = None) -> discord.Message:
        """Send a standardized embed message."""
        embed = discord.Embed(title=title, description=description, color=color)
        
        if fields:
            for field in fields:
                safe_embed_field(
                    embed,
                    field.get('name', 'Field'),
                    field.get('value', 'No value'),
                    field.get('inline', True)
                )
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        if footer:
            embed.set_footer(text=footer)
        
        # Handle both Context and Interaction
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                return await ctx.followup.send(embed=embed)
            else:
                return await ctx.response.send_message(embed=embed)
        else:
            return await ctx.send(embed=embed)
    
    async def send_error_embed(self, ctx: Union[commands.Context, discord.Interaction],
                              title: str, description: str = None) -> discord.Message:
        """Send a standardized error embed."""
        return await self.send_embed(ctx, f"❌ {title}", description, color=0xff0000)
    
    async def send_success_embed(self, ctx: Union[commands.Context, discord.Interaction],
                                title: str, description: str = None) -> discord.Message:
        """Send a standardized success embed."""
        return await self.send_embed(ctx, f"✅ {title}", description, color=0x00ff00)
    
    async def send_info_embed(self, ctx: Union[commands.Context, discord.Interaction],
                             title: str, description: str = None) -> discord.Message:
        """Send a standardized info embed."""
        return await self.send_embed(ctx, f"📊 {title}", description, color=0x3498db)
    
    async def handle_hybrid_response(self, ctx: commands.Context, response: Any) -> None:
        """Handle response for hybrid commands (slash and traditional)."""
        if hasattr(ctx, 'interaction') and ctx.interaction:
            if isinstance(response, discord.Embed):
                await ctx.send(embed=response)
            else:
                await ctx.send(response)
        else:
            if isinstance(response, discord.Embed):
                await ctx.send(embed=response)
            else:
                await ctx.send(response)
    
    async def defer_if_slash(self, ctx: commands.Context) -> None:
        """Defer response if this is a slash command."""
        if hasattr(ctx, 'interaction') and ctx.interaction:
            await ctx.defer()
    
    def is_admin(self, member: discord.Member) -> bool:
        """Check if member has admin permissions."""
        return member.guild_permissions.administrator
    
    def is_moderator(self, member: discord.Member) -> bool:
        """Check if member has moderator permissions."""
        return any([
            member.guild_permissions.administrator,
            member.guild_permissions.manage_messages,
            member.guild_permissions.manage_channels,
            member.guild_permissions.manage_guild
        ])


class GameCommandCog(BaseCommandCog):
    """Base class for game-specific command cogs."""
    
    def __init__(self, bot: commands.Bot, game_name: str):
        super().__init__(bot)
        self.game_name = game_name
    
    def format_player_list(self, players: List[discord.Member],
                          show_game_info: bool = False) -> str:
        """Format a list of players for display."""
        if not players:
            return "No players"
        
        formatted = []
        for player in players:
            if show_game_info:
                # Check if player is in game
                activity = self.get_game_activity(player)
                if activity:
                    formatted.append(f"🎮 **{player.display_name}** (In Game)")
                else:
                    formatted.append(f"**{player.display_name}**")
            else:
                formatted.append(f"**{player.display_name}**")
        
        return "\n".join(formatted)
    
    def get_game_activity(self, member: discord.Member) -> Optional[discord.Activity]:
        """Get game activity for a member."""
        if not member.activities:
            return None
        
        for activity in member.activities:
            if isinstance(activity, discord.Game) and self.game_name.lower() in activity.name.lower():
                return activity
            elif hasattr(activity, 'application_id'):
                # Check for specific game application IDs
                if self.is_target_game(activity):
                    return activity
        
        return None
    
    def is_target_game(self, activity: discord.Activity) -> bool:
        """Check if activity is for the target game (override in subclass)."""
        return False
    
    def count_players_in_game(self, guild: discord.Guild) -> int:
        """Count how many players are currently in the game."""
        count = 0
        for member in guild.members:
            if not member.bot and self.get_game_activity(member):
                count += 1
        return count


class PaginatedEmbed:
    """Helper class for creating paginated embeds."""
    
    def __init__(self, title: str, color: int = 0x3498db,
                 items_per_page: int = 10, footer_base: str = ""):
        self.title = title
        self.color = color
        self.items_per_page = items_per_page
        self.footer_base = footer_base
        self.items: List[str] = []
    
    def add_item(self, item: str) -> None:
        """Add an item to the paginated list."""
        self.items.append(item)
    
    def add_items(self, items: List[str]) -> None:
        """Add multiple items to the paginated list."""
        self.items.extend(items)
    
    def get_page(self, page: int = 1) -> discord.Embed:
        """Get a specific page as an embed."""
        total_pages = self.get_total_pages()
        page = max(1, min(page, total_pages))  # Clamp to valid range
        
        start_idx = (page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = self.items[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"{self.title} (Page {page}/{total_pages})",
            description="\n".join(page_items) if page_items else "No items",
            color=self.color
        )
        
        footer = self.footer_base
        if total_pages > 1:
            footer += f" | Page {page} of {total_pages}"
        
        if footer:
            embed.set_footer(text=footer)
        
        return embed
    
    def get_total_pages(self) -> int:
        """Get total number of pages."""
        if not self.items:
            return 1
        return (len(self.items) + self.items_per_page - 1) // self.items_per_page
    
    def get_all_pages(self) -> List[discord.Embed]:
        """Get all pages as a list of embeds."""
        return [self.get_page(i) for i in range(1, self.get_total_pages() + 1)]


class ConfirmationView(discord.ui.View):
    """A simple yes/no confirmation view."""
    
    def __init__(self, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None
        self.interaction: Optional[discord.Interaction] = None
    
    @discord.ui.button(label='Yes', style=discord.ButtonStyle.success, emoji='✅')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.interaction = interaction
        self.stop()
    
    @discord.ui.button(label='No', style=discord.ButtonStyle.danger, emoji='❌')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.interaction = interaction
        self.stop()
    
    async def on_timeout(self) -> None:
        """Called when the view times out."""
        self.value = False
        for item in self.children:
            item.disabled = True


async def require_confirmation(ctx: commands.Context, prompt: str,
                              timeout: float = 30.0) -> bool:
    """Ask for user confirmation with buttons."""
    view = ConfirmationView(timeout=timeout)
    
    embed = discord.Embed(
        title="❓ Confirmation Required",
        description=prompt,
        color=0xffcc00
    )
    
    message = await ctx.send(embed=embed, view=view)
    
    # Wait for interaction
    await view.wait()
    
    # Update the message based on response
    if view.value is None:  # Timeout
        embed.color = 0x808080
        embed.description = f"{prompt}\n\n⏱️ Confirmation timed out."
        await message.edit(embed=embed, view=None)
        return False
    elif view.value:  # Confirmed
        if view.interaction and view.interaction.user == ctx.author:
            await view.interaction.response.defer()
            return True
        return False
    else:  # Cancelled
        if view.interaction and view.interaction.user == ctx.author:
            await view.interaction.response.defer()
            embed.color = 0xff0000
            embed.description = f"{prompt}\n\n❌ Cancelled."
            await message.edit(embed=embed, view=None)
        return False
