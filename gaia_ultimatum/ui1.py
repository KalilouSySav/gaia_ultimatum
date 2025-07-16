import pygame

class UIManager:
    def __init__(self, screen, screen_width, screen_height):
        self.screen = screen
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.font = pygame.font.Font(None, 36)  # Choisissez une police appropriée
        self.main_menu_options = ["Recommencer", "Reprendre", "Quitter"] # Options du menu ici

    def draw_main_menu(self, selected_option=0):
        """Affiche le menu principal du jeu.

        Args:
            selected_option: L'index de l'option actuellement sélectionnée (0 = Recommencer, 1 = Reprendre, 2 = Quitter).
        """
        menu_y = self.screen_height // 2 - 50  # Calculer menu_y une seule fois.

        for i, option in enumerate(self.main_menu_options): # Utiliser self.main_menu_options
            color = (255, 255, 255)
            if i == selected_option:
                color = (255, 255, 0)
            text = self.font.render(option, True, color)
            text_rect = text.get_rect(center=(self.screen_width // 2, menu_y + i * 50))
            self.screen.blit(text, text_rect)  # Utiliser self.screen

    def load_icons(self):
        """Charge les icônes du menu."""
        try:
            self.icons = {
                "Eau": pygame.image.load("data/images/water_icon.png"),
                "Feu": pygame.image.load("data/images/fire_icon.png"),
                "Terre": pygame.image.load("data/images/earth_icon.png"),
                "Air": pygame.image.load("data/images/air_icon.png"),
                "Vie": pygame.image.load("data/images/life_icon.png"),
            }
            # Redimensionner les icônes si nécessaire
            for icon_name, icon in self.icons.items():
                self.icons[icon_name] = pygame.transform.scale(icon, (50, 50))  # Exemple de taille 50x50
        except FileNotFoundError:
            print("Erreur : Icône non trouvée.  Utilisation d'une image par défaut.")
            self.icons = {} # Créer un dictionnaire vide pour éviter les erreurs plus tard

    def draw_progress_bar(self, x, y, width, height, progress, max_progress, icon_name=None):
        """Dessine une barre de progression."""
        pygame.draw.rect(self.screen, (200, 200, 200), (x, y, width, width * height))  # Fond gris
        pygame.draw.rect(self.screen, (0, 255, 0), (x, y, width * (progress / max_progress), width * height)) # Barre verte

        if icon_name and icon_name in self.icons:
            icon = self.icons[icon_name]
            icon = pygame.transform.scale(icon, (50, 50))
            self.screen.blit(icon, (x - 60 , y))

    def display_notification(self, message, duration=3000):  # Durée en millisecondes
        """Affiche une notification temporaire à l'écran."""
        text = self.font.render(message, True, (255, 255, 255))
        text_rect = text.get_rect(center=(self.width // 2, self.height - 50))

        self.screen.blit(text, text_rect)
        pygame.display.flip()

        start_time = pygame.time.get_ticks()
        while pygame.time.get_ticks() - start_time < duration:  # Afficher pendant la durée spécifiée
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()  # Sortir proprement si l'utilisateur ferme la fenêtre

            pygame.time.Clock().tick(60) #Limiter le fps

    def handle_menu_input(self, event, selected_option):
        """Gère les entrées du menu principal (clavier)."""

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                selected_option = (selected_option - 1) % len(self.main_menu_options) # Boucler vers le haut
            elif event.key == pygame.K_DOWN:
                selected_option = (selected_option + 1) % len(self.main_menu_options) # Boucler vers le bas
            elif event.key == pygame.K_RETURN: # Valider la sélection
                if selected_option == 0:
                    return "Recommencer"  # Ou la logique correspondante
                elif selected_option == 1:
                    return "Reprendre"  # Ou la logique correspondante
                elif selected_option == 2:
                    return "Quitter"  # Ou la logique correspondante
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Clic gauche
                for i, rect in enumerate(self.menu_rects):
                    if rect.collidepoint(event.pos): # Vérifier si le clic est sur une option
                        if i == 0:
                            return "Recommencer"  # Ou la logique correspondante
                        elif i == 1:
                            return "Reprendre"  # Ou la logique correspondante
                        elif i == 2:
                            return "Quitter" # Ou la logique correspondante

        return selected_option  # Renvoyer la nouvelle option sélectionnée

