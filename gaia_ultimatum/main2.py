import pygame
import sys
from config import *
from game import *
from ui import *
from graphics import *

pygame.font.init()
fenetre = pygame.display.set_mode((largeur, hauteur))
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Gaia Ultimatum")

if __name__ == "__main__":
   clock = pygame.time.Clock()
   mouse_pos = pygame.mouse.get_pos()

   catastrophes = load_catastrophes()
   main_menu(screen, clock, mouse_pos, catastrophes)