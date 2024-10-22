import discord
from discord.ext import commands, tasks
import re
from datetime import datetime, timedelta, timezone

TOKEN = ''  
SOURCE_CHANNEL_ID =   
DESTINATION_CHANNEL_ID =   
WELCOME_CHANNEL_ID =   
CHECK_ROLE_HOURS = 42  
VOICE_CHANNEL_THRESHOLD = timedelta(hours=CHECK_ROLE_HOURS)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.voice_states = True  # Нам нужны права для отслеживания голосовых каналов

bot = commands.Bot(command_prefix='!', intents=intents)

# Регулярное выражение для поиска ссылок
link_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

# Регулярное выражение для поиска сообщений типа "Testsubj запрыгивает на сервер."
join_message_pattern = re.compile(r'^[^\s]+ запрыгивает на сервер\.$')


voice_sessions = {}

@bot.event
async def on_ready():
    print(f'Бот {bot.user} подключен и готов к работе.')
    source_channel = bot.get_channel(SOURCE_CHANNEL_ID)
    destination_channel = bot.get_channel(DESTINATION_CHANNEL_ID)
    
    if source_channel:
        print(f'Бот имеет доступ к исходному каналу: {source_channel.name}')
    else:
        print(f'Не удалось получить доступ к исходному каналу с ID: {SOURCE_CHANNEL_ID}')
        
    if destination_channel:
        print(f'Бот имеет доступ к целевому каналу: {destination_channel.name}')
    else:
        print(f'Не удалось получить доступ к целевому каналу с ID: {DESTINATION_CHANNEL_ID}')
    
    # Запускаем задачу для проверки сообщений за последние три дня
    await fetch_and_process_old_messages(source_channel, destination_channel)
    
    # Проверяем участников, которые присоединились за последнюю неделю
    await check_recent_members()
    
    # Запускаем задачу для проверки голосового времени
    check_voice_time.start()

async def fetch_and_process_old_messages(source_channel, destination_channel):
    now = datetime.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)
    async for message in source_channel.history(limit=None, after=one_month_ago):
        print(f'Проверка старого сообщения: {message.content}')
        match = link_pattern.search(message.content)
        if match:
            print(f'Старое сообщение содержит ссылку: {match.group(0)}')
            if destination_channel:
                print(f'Целевой канал найден: {destination_channel.name}')
                try:
                    await destination_channel.send(message.content)
                    print(f'Старое сообщение успешно переслано.')
                    await message.delete()  # Удаление оригинального сообщения
                    print(f'Старое сообщение успешно удалено.')
                except discord.Forbidden:
                    print(f'Ошибка: Недостаточно прав для пересылки или удаления старого сообщения.')
                except discord.HTTPException as e:
                    print(f'Ошибка HTTP при пересылке или удалении старого сообщения: {e}')

async def check_recent_members():
    now = datetime.now(timezone.utc)
    one_week_ago = now - timedelta(days=7)
    guild = bot.guilds[0]  # Получаем первый сервер, к которому подключен бот
    welcome_channel = bot.get_channel(WELCOME_CHANNEL_ID)
    
    for member in guild.members:
        if member.joined_at and member.joined_at >= one_week_ago:
            print(f'{member.name} присоединился {member.joined_at}. Отправляю приветственное сообщение.')
            role = discord.utils.get(guild.roles, name="Не заходит")
            if role:
                try:
                    await member.add_roles(role)  # Добавляем роль
                    await welcome_channel.send(f"Добро пожаловать, {member.mention}! "
                                               "Вам присвоена роль 'Не заходит'. Заходите чаще, чтобы её изменить!")
                    print(f'Роль "Не заходит" успешно назначена пользователю {member.name}.')
                except discord.Forbidden:
                    print("Недостаточно прав для назначения роли.")
                except discord.HTTPException as e:
                    print(f'Ошибка HTTP при назначении роли: {e}')
            else:
                print("Роль 'Не заходит' не найдена.")
        else:
            print(f'{member.name} присоединился раньше {one_week_ago}, приветствие не требуется.')

@bot.event
async def on_voice_state_update(member, before, after):
    
    if before.channel is None and after.channel is not None:
        voice_sessions[member.id] = datetime.now(timezone.utc)
        print(f"{member.name} присоединился к голосовому каналу {after.channel.name}")
    
    
    elif before.channel is not None and after.channel is None:
        if member.id in voice_sessions:
            start_time = voice_sessions.pop(member.id)
            duration = datetime.now(timezone.utc) - start_time
            
            # Добавляем проведенное время участнику
            if not hasattr(member, 'total_voice_time'):
                member.total_voice_time = timedelta(0)
            member.total_voice_time += duration
            print(f"{member.name} покинул голосовой канал. Проведенное время: {duration}. Общее время: {member.total_voice_time}")

# Ежемесячная проверка для изменения ролей
@tasks.loop(hours=24)  
async def check_voice_time():
    now = datetime.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)
    guild = bot.guilds[0]  # Получаем сервер
    role_inactive = discord.utils.get(guild.roles, name="Не заходит")
    role_active = discord.utils.get(guild.roles, name="Иногда заходит")
    
    if not role_inactive or not role_active:
        print("Роли 'Не заходит' или 'Иногда заходит' не найдены.")
        return

    for member in guild.members:
        if hasattr(member, 'total_voice_time') and member.total_voice_time >= VOICE_CHANNEL_THRESHOLD:
            # Если участник провел в голосовых каналах больше 42 часов, изменяем роль
            if role_inactive in member.roles:
                await member.remove_roles(role_inactive)
                await member.add_roles(role_active)
                print(f"Роль участника {member.name} изменена на 'Иногда заходит'.")
        else:
            print(f"{member.name} не набрал нужное время в голосовых каналах.")

@bot.event
async def on_message(message):
    print(f'Новое сообщение в канале {message.channel.id}: {message.content}')
    
    # Проверка на сообщение типа "Testsubj запрыгивает на сервер." только в нужном канале
    if message.channel.id == SOURCE_CHANNEL_ID:
        if join_message_pattern.match(message.content):
            print(f'Сообщение соответствует шаблону "запрыгивает на сервер": {message.content}')
            try:
                await message.delete()
                print(f'Сообщение успешно удалено.')
            except discord.Forbidden:
                print(f'Ошибка: Недостаточно прав для удаления сообщения.')
            except discord.HTTPException as e:
                print(f'Ошибка HTTP при удалении сообщения: {e}')
            return  # Прекращаем дальнейшую обработку, если сообщение было удалено
        
        # Проверка, содержит ли сообщение ссылку с помощью регулярного выражения
        match = link_pattern.search(message.content)
        if match:
            print(f'Сообщение содержит ссылку: {match.group(0)}')
            destination_channel = bot.get_channel(DESTINATION_CHANNEL_ID)
            if destination_channel:
                print(f'Целевой канал найден: {destination_channel.name}')
                try:
                    await destination_channel.send(message.content)
                    print(f'Сообщение успешно переслано.')
                    await message.delete()  # Удаление оригинального сообщения
                    print(f'Сообщение успешно удалено.')
                except discord.Forbidden:
                    print(f'Ошибка: Недостаточно прав для пересылки или удаления сообщения.')
                except discord.HTTPException as e:
                    print(f'Ошибка HTTP при пересылке или удалении сообщения: {e}')
            else:
                print('Целевой канал не найден.')
        else:
            print('Сообщение не содержит ссылки.')
    
    await bot.process_commands(message)

bot.run(TOKEN)
