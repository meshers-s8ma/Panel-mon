# app/models/models.py

from app import db
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, AnonymousUserMixin
import enum

# --- Ассоциативная таблица для структуры "Изделие-Компонент" (Bill of Materials) ---
class AssemblyComponent(db.Model):
    """
    Связующая модель для реализации отношения "многие-ко-многим" между деталями.
    Показывает, какая деталь (child) входит в состав какой сборки (parent) и в каком количестве.
    """
    __tablename__ = 'AssemblyComponents'
    parent_id = db.Column(db.String, db.ForeignKey('Parts.part_id'), primary_key=True)
    child_id = db.Column(db.String, db.ForeignKey('Parts.part_id'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    # Отношения для удобного доступа к объектам Part из этой модели
    child = db.relationship('Part', foreign_keys=[child_id], back_populates='parent_associations')
    parent = db.relationship('Part', foreign_keys=[parent_id], back_populates='child_associations')

# --- Справочники ---

class Stage(db.Model):
    """Модель для справочника производственных этапов."""
    __tablename__ = 'Stages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class RouteTemplate(db.Model):
    """Модель для шаблонов технологических маршрутов."""
    __tablename__ = 'RouteTemplates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, index=True)
    stages = db.relationship('RouteStage', backref='template', cascade="all, delete-orphan")

class RouteStage(db.Model):
    """Связующая модель для определения порядка этапов в маршруте."""
    __tablename__ = 'RouteStages'
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('RouteTemplates.id'), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey('Stages.id'), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    stage = db.relationship('Stage')

# --- Пользователи и права доступа ---

class Permission:
    """Класс-перечисление для битовых флагов прав доступа."""
    ADD_PARTS = 1
    EDIT_PARTS = 2
    DELETE_PARTS = 4
    GENERATE_QR = 8
    VIEW_AUDIT_LOG = 16
    MANAGE_STAGES = 32
    MANAGE_ROUTES = 64
    VIEW_REPORTS = 128
    MANAGE_USERS = 256
    ADMIN = 512

class Role(db.Model):
    """Модель для ролей пользователей."""
    __tablename__ = 'Roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    default = db.Column(db.Boolean, default=False, index=True)
    permissions = db.Column(db.Integer)
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Role, self).__init__(**kwargs)
        if self.permissions is None: self.permissions = 0

    def add_permission(self, perm): self.permissions |= perm
    def remove_permission(self, perm): self.permissions &= ~perm
    def reset_permissions(self): self.permissions = 0
    def has_permission(self, perm): return self.permissions & perm == perm

    @staticmethod
    def insert_roles():
        roles_map = {
            'Operator': [Permission.GENERATE_QR],
            'Manager': [
                Permission.ADD_PARTS, Permission.EDIT_PARTS, Permission.DELETE_PARTS,
                Permission.GENERATE_QR, Permission.VIEW_AUDIT_LOG, Permission.VIEW_REPORTS
            ],
            'Administrator': [
                Permission.ADD_PARTS, Permission.EDIT_PARTS, Permission.DELETE_PARTS,
                Permission.GENERATE_QR, Permission.VIEW_AUDIT_LOG, Permission.MANAGE_STAGES,
                Permission.MANAGE_ROUTES, Permission.VIEW_REPORTS, Permission.MANAGE_USERS,
                Permission.ADMIN
            ]
        }
        default_role = 'Operator'
        with db.session.no_autoflush:
            for name, perms in roles_map.items():
                role = Role.query.filter_by(name=name).first()
                if role is None: role = Role(name=name); db.session.add(role)
                role.reset_permissions()
                for perm in perms: role.add_permission(perm)
                role.default = (role.name == default_role)
        db.session.commit()

class User(UserMixin, db.Model):
    """Модель пользователя."""
    __tablename__ = 'Users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey('Roles.id'))
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None: self.role = Role.query.filter_by(default=True).first()
    def can(self, perm): return self.role is not None and self.role.has_permission(perm)
    def is_admin(self): return self.can(Permission.ADMIN)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class AnonymousUser(AnonymousUserMixin):
    def can(self, permissions): return False
    def is_admin(self): return False

# --- Основные сущности ---

class Part(db.Model):
    """Модель для детали/изделия/сборки."""
    __tablename__ = 'Parts'
    part_id = db.Column(db.String, primary_key=True)
    product_designation = db.Column(db.String, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    material = db.Column(db.String(150), nullable=False)
    size = db.Column(db.String(100), nullable=True)
    date_added = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    current_status = db.Column(db.String, default='На складе')
    last_update = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    quantity_total = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    quantity_completed = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    quantity_scrapped = db.Column(db.Integer, nullable=False, default=0, server_default='0') # НОВОЕ ПОЛЕ
    drawing_filename = db.Column(db.String(255), nullable=True)
    
    route_template_id = db.Column(db.Integer, db.ForeignKey('RouteTemplates.id'), nullable=True)
    route_template = db.relationship('RouteTemplate')
    
    responsible_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=True)
    responsible = db.relationship('User', backref='responsible_parts', foreign_keys=[responsible_id])
    
    # --- ИЗМЕНЕНИЕ: Связи "многие-ко-многим" через `AssemblyComponent` ---
    # Показывает, из каких компонентов состоит эта деталь (если она сборка)
    child_associations = db.relationship('AssemblyComponent', foreign_keys=[AssemblyComponent.parent_id], back_populates='parent', cascade="all, delete-orphan", lazy='dynamic')
    # Показывает, в какие сборки входит эта деталь
    parent_associations = db.relationship('AssemblyComponent', foreign_keys=[AssemblyComponent.child_id], back_populates='child', cascade="all, delete-orphan", lazy='dynamic')
    
    history = db.relationship('StatusHistory', backref='part', lazy=True, cascade="all, delete-orphan")
    notes = db.relationship('PartNote', backref='part', lazy=True, cascade="all, delete-orphan")

# --- Исторические/Логовые сущности ---

class StatusType(enum.Enum):
    """Перечисление для типов статусов, включая брак."""
    COMPLETED = 'completed'
    REWORK = 'rework'
    SCRAPPED = 'scrapped'

class StatusHistory(db.Model):
    """Модель для истории прохождения этапов."""
    __tablename__ = 'StatusHistory'
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String, db.ForeignKey('Parts.part_id'), nullable=False, index=True)
    status = db.Column(db.String, nullable=False)
    operator_name = db.Column(db.String, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    status_type = db.Column(db.Enum(StatusType), nullable=False, default=StatusType.COMPLETED) # НОВОЕ ПОЛЕ

class AuditLog(db.Model):
    """Модель для журнала всех действий в системе."""
    __tablename__ = 'AuditLogs'
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String, nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False, default='general', server_default='general', index=True)

class PartNote(db.Model):
    """Модель для примечаний к деталям."""
    __tablename__ = 'PartNotes'
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String, db.ForeignKey('Parts.part_id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey('Stages.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    text = db.Column(db.Text, nullable=False)
    author = db.relationship('User', backref='notes', foreign_keys=[user_id])
    stage = db.relationship('Stage')

class ResponsibleHistory(db.Model):
    """Модель для истории смены ответственных за деталь."""
    __tablename__ = 'ResponsibleHistory'
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String, db.ForeignKey('Parts.part_id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    part = db.relationship('Part', backref=db.backref('responsible_history', cascade="all, delete-orphan"))
    user = db.relationship('User', foreign_keys=[user_id])