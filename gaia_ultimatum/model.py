import pygame
import json

class SkillType:
    FOUNDATION = "Fondations"
    AMPLIFICATION = "Amplification"
    TRANSFORMATION = "Transformation"

class SkillNode:
    def __init__(self, x, y, width, height, name, description, cost, level=0, skill_type=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.name = name
        self.description = description
        self.cost = cost
        self.level = level
        self.skill_type = skill_type
        self.color = (0, 0, 255)  # Bleu par défaut
        self.update_color()

    def update_color(self):
        if self.skill_type == SkillType.FOUNDATION:
            self.color = (0, 0, 255)  # Bleu
        elif self.skill_type == SkillType.AMPLIFICATION:
            self.color = (0, 255, 0)  # Vert
        elif self.skill_type == SkillType.TRANSFORMATION:
            self.color = (255, 0, 0)  # Rouge

    def draw(self, screen):
        pygame.draw.rect(screen, self.color, self.rect)
        font = pygame.font.Font(None, 24)
        text = font.render(self.name, True, (255, 255, 255))
        text_rect = text.get_rect(center=self.rect.center)
        screen.blit(text, text_rect)

    def is_clicked(self, pos):
        return self.rect.collidepoint(pos)

class Catastrophe:
    def __init__(self, name):
        self.name = name
        self.skills = {}
        self.load_data()


    def get_skill(self, name):
        return self.skills.get(name)

    def get_skills_by_type(self, skill_type):
        return [
            (name, details)
            for name, details in self.skills.items()
            if details["type"] == skill_type
        ]

# Exemple d'utilisation
pygame.init()
screen = pygame.display.set_mode((800, 600))

eau_catastrophe = Catastrophe("Eau")

# Récupération des compétences par type
fondation_skills = eau_catastrophe.get_skills_by_type(SkillType.FOUNDATION)
amplification_skills = eau_catastrophe.get_skills_by_type(SkillType.AMPLIFICATION)
transformation_skills = eau_catastrophe.get_skills_by_type(
    SkillType.TRANSFORMATION
)

# Création des noeuds de compétences
skills = []
x = 100
y = 100
width = 150
height = 80
for name, details in fondation_skills:
    skills.append(
        SkillNode(
            x, y, width, height, name, details["description"], details["cost"], skill_type=SkillType.FOUNDATION
        )
    )
    y += 100

x = 300
y = 100
for name, details in amplification_skills:
    skills.append(
        SkillNode(
            x, y, width, height, name, details["description"], details["cost"], skill_type=SkillType.AMPLIFICATION
        )
    )
    y += 100

x = 500
y = 100
for name, details in transformation_skills:
    skills.append(
        SkillNode(
            x, y, width, height, name, details["description"], details["cost"], skill_type=SkillType.TRANSFORMATION
        )
    )
    y += 100

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            for skill in skills:
                if skill.is_clicked(event.pos):
                    print(f"Compétence cliquée: {skill.name}")

    screen.fill((0, 0, 0))
    for skill in skills:
        skill.draw(screen)
    pygame.display.flip()

pygame.quit()