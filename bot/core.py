class BotCore:
    def __init__(self):
        self.app = None
    
    def setup(self, app):
        self.app = app
        # Здесь можно добавить инициализацию базы данных и других компонентов

bot_core = BotCore()