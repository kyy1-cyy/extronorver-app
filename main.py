import kivy
kivy.require('2.3.1')

import os
import asyncio
import threading
from datetime import datetime
import discord
from dotenv import load_dotenv

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.core.window import Window
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.utils import get_color_from_hex

import webbrowser
import re

# Custom Label to handle mouse cursor changes on hover
class LinkLabel(Label):
    def __init__(self, **kwargs):
        super(LinkLabel, self).__init__(**kwargs)
        Window.bind(mouse_pos=self._on_mouse_pos)
        self._is_hovering = False

    def _on_mouse_pos(self, window, pos):
        # Check if the mouse is over the label
        if self.collide_point(*pos):
            if not self._is_hovering:
                Window.set_system_cursor('hand')
                self._is_hovering = True
        else:
            if self._is_hovering:
                Window.set_system_cursor('arrow')
                self._is_hovering = False

# Helper to get the first message from a thread history
async def anext(iterator):
    return await iterator.__anext__()

class ExtroNorverApp(App):
    
    selected_row = None # To keep track of the highlighted row

    def build(self):
        load_dotenv()
        self.DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
        self.CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
        self.all_posts = [] # Initialize to prevent crash
        Window.clearcolor = get_color_from_hex('#262626')
        self.root_layout = BoxLayout(orientation='vertical')

        # Header with app title, search bar, and Tested Games button
        header_layout = BoxLayout(size_hint_y=None, height=100, padding=20, spacing=20)
        app_title = Label(text='ExtroNorver', font_size='30sp', bold=True, size_hint_x=0.4)

        self.search_input = TextInput(
            hint_text='Search games...',
            size_hint_x=0.4,
            multiline=False,
            opacity=0,
            disabled=True
        )
        self.search_input.bind(text=self.filter_posts)

        self.tested_button = Button(text='Tested Games', size_hint_x=0.2, opacity=0, disabled=True)
        self.tested_button.bind(on_release=self.show_tested_games_popup)

        header_layout.add_widget(app_title)
        header_layout.add_widget(self.search_input)
        header_layout.add_widget(self.tested_button)
        self.root_layout.add_widget(header_layout)

        # --- Separator ---
        separator = Widget(size_hint_y=None, height=2)
        with separator.canvas:
            Color(*get_color_from_hex('#4f4f4f'))
            separator.rect = Rectangle(pos=separator.pos, size=separator.size)
        separator.bind(pos=self.update_rect, size=self.update_rect)
        self.root_layout.add_widget(separator)

        # --- Scrollable Post List ---
        self.post_list = GridLayout(cols=2, spacing=10, size_hint_y=None)
        self.post_list.bind(minimum_height=self.post_list.setter('height'))
        
        # Add a fetching label initially
        self.fetching_label = Label(text='Fetching posts...', size_hint_y=None, height=100)
        self.post_list.add_widget(self.fetching_label)

        scroll_view = ScrollView(size_hint=(1, 1), scroll_type=['bars'], bar_width=10)
        scroll_view.add_widget(self.post_list)
        self.root_layout.add_widget(scroll_view)

        threading.Thread(target=self.run_discord_bot, daemon=True).start()
        return self.root_layout

    def run_discord_bot(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start_bot())

    async def start_bot(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.guilds = True
        intents.message_content = True # Required for reading message content

        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            print(f'Logged in as {client.user}')
            await self.fetch_and_update_posts(client)

        @client.event
        async def on_thread_create(thread):
            if thread.parent_id == self.CHANNEL_ID:
                print(f"New thread detected: {thread.name}")
                await self.fetch_and_update_posts(client)

        await client.start(self.DISCORD_TOKEN)

    async def fetch_and_update_posts(self, client):
        channel = client.get_channel(self.CHANNEL_ID)
        if not isinstance(channel, discord.ForumChannel):
            print("Channel is not a ForumChannel")
            return

        posts = []
        try:
            threads = channel.threads
            archived_threads = [t async for t in channel.archived_threads(limit=None)]
            all_threads = threads + archived_threads

            for thread in all_threads:
                try:
                    first_message = await anext(thread.history(limit=1, oldest_first=True))
                    content = first_message.content
                    all_messages = [msg.content async for msg in thread.history(limit=None)]
                    posts.append({'title': thread.name, 'content': content, 'created_at': thread.created_at, 'thread_id': thread.id, 'all_messages': all_messages})
                except StopAsyncIteration:
                    posts.append({'title': thread.name, 'content': 'No content found.', 'created_at': thread.created_at, 'thread_id': thread.id, 'all_messages': []})
        except Exception as e:
            print(f"Error fetching threads: {e}")

        posts.sort(key=lambda p: p['created_at'], reverse=True)
        self.all_posts = posts
        display_posts = [p for p in posts if 'tested' not in p['title'].lower()]
        Clock.schedule_once(lambda dt: self.update_post_list(display_posts))

    def update_post_list(self, posts):
        self.post_list.clear_widgets()
        if not posts:
            self.post_list.cols = 1 # Temporarily change to 1 column for centering
            no_posts_label = Label(
                text='No posts found.',
                halign='center',
                valign='middle',
                size_hint_y=None,
                height=self.post_list.parent.height
            )
            no_posts_label.bind(size=no_posts_label.setter('text_size'))
            self.post_list.add_widget(no_posts_label)
            return

        # Ensure the layout is set to 2 columns for displaying posts
        self.post_list.cols = 2

        # Make search and tested button visible now that posts are loaded
        self.search_input.opacity = 1
        self.search_input.disabled = False
        self.tested_button.opacity = 1
        self.tested_button.disabled = False

        # Remove fetching label if it exists
        if hasattr(self, 'fetching_label') and self.fetching_label.parent:
            self.post_list.remove_widget(self.fetching_label)
        
        header_name = Label(text='Game Name', bold=True, size_hint_y=None, height=50, halign='left', padding_x=20, size_hint_x=0.75)
        header_date = Label(text='Post Date', bold=True, size_hint_y=None, height=50, halign='right', padding_x=20, size_hint_x=0.25)
        self.post_list.add_widget(header_name)
        self.post_list.add_widget(header_date)
        
        for post in posts:
            # Create a container for the name button to handle padding correctly
            name_container = BoxLayout(size_hint_x=0.75, padding=(20, 0, 0, 0)) 
            name_button = Button(
                text=post['title'],
                size_hint_y=None, height=80, size_hint_x=1,
                halign='left', valign='middle',
                shorten=True, shorten_from='right',
                background_color=(0,0,0,0)
            )
            name_button.bind(size=lambda instance, value: setattr(instance, 'text_size', (instance.width, None)))
            name_container.add_widget(name_button)

            date_label = Label(
                text=post['created_at'].strftime('%Y-%m-%d'),
                size_hint_y=None, height=80, size_hint_x=0.25,
                halign='right', valign='middle', padding_x=20
            )

            name_button.post_data = post
            name_button.date_label = date_label
            name_button.bind(on_release=self.on_row_press)
            
            self.post_list.add_widget(name_container)
            self.post_list.add_widget(date_label)

            separator_widget = Widget(size_hint_y=None, height=1)
            with separator_widget.canvas.before:
                Color(0.25, 0.25, 0.25, 1)
                separator_widget.rect = Rectangle(pos=(self.post_list.x, 0), size=(self.post_list.width, 1))
            separator_widget.bind(pos=self.update_rect, size=self.update_rect)
            self.post_list.add_widget(separator_widget)

            placeholder = Widget(size_hint_y=None, height=1)
            self.post_list.add_widget(placeholder)

    def on_row_press(self, button_instance):
        if self.selected_row and self.selected_row != button_instance:
            self.selected_row.background_color = (0,0,0,0)
            self.selected_row.date_label.color = (1,1,1,1)

        button_instance.background_color = (0.1, 0.5, 0.8, 0.5)
        button_instance.date_label.color = get_color_from_hex('#1a8cff')
        self.selected_row = button_instance
        
        self.show_post_popup(button_instance.post_data)

    def filter_posts(self, instance, search_text):
        search_text = search_text.lower().strip()
        current_posts = [p for p in self.all_posts if 'tested' not in p['title'].lower()]

        if not search_text:
            self.update_post_list(current_posts)
            return

        filtered_posts = [p for p in current_posts if search_text in p['title'].lower()]
        self.update_post_list(filtered_posts)

    def update_rect(self, instance, value):
        if hasattr(instance, 'bg_rect'):
            instance.bg_rect.pos = instance.pos
            instance.bg_rect.size = instance.size
        elif hasattr(instance, 'rect'):
            instance.rect.pos = (instance.x, instance.y)
            instance.rect.size = (instance.width, instance.height)
        elif hasattr(self, 'list_bg') and instance == self.list_container:
            self.list_bg.pos = instance.pos
            self.list_bg.size = instance.size

    def show_post_popup(self, post):
        popup_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Add the title label at the top of the popup content
        title_label = Label(text=post['title'], bold=True, size_hint_y=None, height=40)
        popup_layout.add_widget(title_label)

        # Add a separator
        separator = Widget(size_hint_y=None, height=1)
        with separator.canvas:
            Color(0.5, 0.5, 0.5, 1)
            # Store the rectangle on the widget itself, not the app instance
            separator.rect = Rectangle(pos=separator.pos, size=separator.size)

        # Use a binding to update the rectangle's position and size
        def update_rect(instance, value):
            instance.rect.pos = instance.pos
            instance.rect.size = instance.size

        separator.bind(pos=update_rect, size=update_rect)
        popup_layout.add_widget(separator)

        content_text = post.get('content', 'No content available.')

        # Use regex to find all URLs and format them
        url_pattern = r'(https?://\S+)'
        parts = re.split(url_pattern, content_text)
        formatted_text = ''
        urls = []
        for i, part in enumerate(parts):
            if re.match(url_pattern, part):
                urls.append(part)
                formatted_text += f'[ref={len(urls)-1}][color=1a8cff]{part}[/color][/ref]'
            else:
                formatted_text += part.replace('[', '&bl;').replace(']', '&br;') # Escape brackets

        def open_url(instance, ref_index):
            webbrowser.open(urls[int(ref_index)])

        content_label = LinkLabel(
            text=formatted_text,
            markup=True,
            size_hint_y=None
        )
        if urls:
            content_label.bind(on_ref_press=open_url)

        # Enable text wrapping for the content label
        content_label.bind(width=lambda *x: content_label.setter('text_size')(content_label, (content_label.width, None)))
        content_label.bind(texture_size=content_label.setter('size'))

        # Use a ScrollView for the content to prevent overflow
        scroll_view = ScrollView(size_hint=(1, 1))
        scroll_view.add_widget(content_label)

        popup_layout.add_widget(scroll_view)

        close_button = Button(text='Close', size_hint_y=None, height=40)
        popup_layout.add_widget(close_button)

        popup = Popup(
            title=post['title'],
            content=popup_layout,
            size_hint=(0.8, 0.8)
        )
        close_button.bind(on_release=popup.dismiss)
        popup.open()

    def show_tested_games_popup(self, instance):
        tested_post = None
        for post in self.all_posts:
            if 'tested' in post['title'].lower():
                tested_post = post
                break
        
        if not tested_post:
            popup = Popup(title='Not Found', content=Label(text='No "Tested" game found.'), size_hint=(0.6, 0.3))
            popup.open()
            return

        messages_text = "\n\n".join(tested_post.get('all_messages', ['No messages.']))
        scroll_content = Label(text=messages_text, size_hint_y=None, halign='left', valign='top')
        scroll_content.bind(width=lambda *x: scroll_content.setter('text_size')(scroll_content, (scroll_content.width, None)))
        scroll_content.bind(texture_size=scroll_content.setter('size'))

        scroll_view = ScrollView(size_hint=(1, 1))
        scroll_view.add_widget(scroll_content)

        popup = Popup(
            title=f"{tested_post['title']} - All Messages",
            content=scroll_view,
            size_hint=(0.8, 0.8)
        )
        popup.open()

if __name__ == '__main__':
    ExtroNorverApp().run()
