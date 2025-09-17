
// cypress/e2e/auth.cy.js

describe('Сценарий аутентификации (вход/выход)', () => {
  
  beforeEach(() => {
    // --- ИЗМЕНЕНИЕ: Устанавливаем размер окна перед каждым тестом ---
    cy.viewport(1280, 720);
    cy.visit('/admin/user/login');
  });

  it('должен показывать ошибку при вводе неверных учетных данных', () => {
    cy.get('input[name="username"]').type('wronguser');
    cy.get('input[name="password"]').type('wrongpassword');
    cy.get('input[type="submit"]').click();

    cy.url().should('include', '/admin/user/login');
    cy.contains('Неверный логин или пароль.').should('be.visible');
  });

  it('должен успешно входить в систему с учетными данными администратора', () => {
    cy.get('input[name="username"]').type('admin');
    cy.get('input[name="password"]').type('password123');
    cy.get('input[type="submit"]').click();

    cy.url().should('eq', Cypress.config().baseUrl + '/');
    cy.contains('h1', 'Панель мониторинга').should('be.visible');
    // Теперь эта проверка должна пройти, так как окно будет достаточно широким
    cy.contains('admin (Administrator)').should('be.visible');
  });

  it('должен успешно выходить из системы после входа', () => {
    cy.get('input[name="username"]').type('admin');
    cy.get('input[name="password"]').type('password123');
    cy.get('input[type="submit"]').click();

    cy.url().should('eq', Cypress.config().baseUrl + '/');

    cy.contains('a', 'Выйти').click();

    cy.url().should('include', '/admin/user/login');
    cy.contains('Вы вышли из системы.').should('be.visible');
    cy.contains('a', 'Войти').should('be.visible');
    cy.contains('a', 'Выйти').should('not.exist');
  });

});