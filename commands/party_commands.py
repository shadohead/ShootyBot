from typing import List
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import get_kicked_user_message, get_max_party_size_message
from config import MESSAGES
from base_commands import BaseCommandCog


class PartyCommands(BaseCommandCog):
    """Commands for managing party settings and members"""
    
    @commands.hybrid_command(
        name="shootykick", 
        description="Kick user from party by username prefix"
    )
    async def kick_user(self, ctx: commands.Context, username: str) -> None:
        """Kick a user from the party by username prefix."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            potential_user_names_list = [username]
            kicked_usernames_list = shooty_context.remove_user_from_everything(potential_user_names_list)
            
            if kicked_usernames_list:
                message = get_kicked_user_message(kicked_usernames_list)
                await ctx.reply(message)
                self.logger.info(f"Kicked users {kicked_usernames_list} from channel {channel_id}")
            else:
                await self.send_error_embed(
                    ctx, 
                    "User Not Found", 
                    f"No users found matching '{username}'"
                )
            
            # Save the context after modification
            context_manager.save_context(channel_id)
            
        except Exception as e:
            self.logger.error(f"Error in kick_user: {e}")
            await self.send_error_embed(ctx, "Kick Failed", "An error occurred while kicking the user")
    
    @commands.hybrid_command(
        name="shootysize", 
        description="Set maximum party size (1-20 players)"
    )
    async def set_session_size(self, ctx: commands.Context, size: str) -> None:
        """Set the maximum party size for sessions."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            if not size.isdigit():
                await self.send_error_embed(
                    ctx, 
                    "Invalid Size", 
                    "Party size must be a positive number"
                )
                return
            
            new_party_max_size = int(size)
            
            # Validate size range
            if new_party_max_size < 1 or new_party_max_size > 20:
                await self.send_error_embed(
                    ctx, 
                    "Invalid Size", 
                    "Party size must be between 1 and 20 players"
                )
                return
            
            old_size = shooty_context.get_party_max_size()
            shooty_context.set_party_max_size(new_party_max_size)
            
            # Save the context after modification
            context_manager.save_context(channel_id)
            
            message = get_max_party_size_message(new_party_max_size)
            await ctx.reply(message)
            
            self.logger.info(f"Changed party size from {old_size} to {new_party_max_size} in channel {channel_id}")
            
        except ValueError:
            await self.send_error_embed(
                ctx, 
                "Invalid Size", 
                "Party size must be a valid number"
            )
        except Exception as e:
            self.logger.error(f"Error in set_session_size: {e}")
            await self.send_error_embed(ctx, "Size Change Failed", "An error occurred while changing party size")
    
    @commands.hybrid_command(
        name="shootyclear",
        description="Clear all users from the current session"
    )
    async def clear_session(self, ctx: commands.Context) -> None:
        """Clear all users from the current session with backup."""
        try:
            channel_id = ctx.channel.id
            shooty_context = context_manager.get_context(channel_id)
            
            # Check if there are users to clear
            all_users = shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)
            if not all_users:
                await self.send_info_embed(
                    ctx,
                    "No Active Session",
                    "There are no users in the current session"
                )
                return
            
            # Backup in case of undo needed
            shooty_context.backup_state()
            
            user_names = [user.name for user in all_users]
            self.logger.info(f"Clearing user sets: {user_names} from channel {channel_id}")
            
            shooty_context.reset_users()
            
            # Save the context after modification
            context_manager.save_context(channel_id)
            
            await self.send_success_embed(
                ctx,
                "Session Cleared",
                f"Removed {len(user_names)} users from the session"
            )
            
        except Exception as e:
            self.logger.error(f"Error in clear_session: {e}")
            await self.send_error_embed(ctx, "Clear Failed", "An error occurred while clearing the session")

async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    await bot.add_cog(PartyCommands(bot))