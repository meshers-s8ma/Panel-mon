
// cypress/e2e/dashboard.cy.js

describe('Тестирование панели мониторинга (дашборда)', () => {

  beforeEach(() => {
    cy.viewport(1280, 720);
    cy.visit('/admin/user/login');
    
    cy.get('input[name="username"]').type('admin');
    cy.get('input[name="password"]').type('password123');
    cy.get('input[type="submit"]').click();

    cy.url().should('eq', Cypress.config().baseUrl + '/');
    cy.contains('h1', 'Панель мониторинга');
  });

  it('должен отображать список изделий и раскрывать детали по клику', () => {
    cy.contains('td', 'Тестовое изделие').should('be.visible');

    cy.contains('td', 'Тестовое изделие').click();

    cy.contains('th', 'Обозначение').should('be.visible');
    
    cy.contains('a', 'CY-TEST-001').should('be.visible');
  });

  it('должен фильтровать изделия с помощью поля поиска', () => {
    cy.contains('td', 'Тестовое изделие').should('be.visible');
    cy.contains('td', 'Другое изделие').should('be.visible');

    cy.log('--- Вводим в поиск "Тестовое" ---');
    cy.get('#searchInput').type('Тестовое');

    cy.contains('td', 'Тестовое изделие').should('be.visible');
    cy.contains('td', 'Другое изделие').should('not.exist');

    cy.log('--- Очищаем поиск и вводим несуществующее ---');
    cy.get('#searchInput').clear().type('Несуществующее изделие 123');

    cy.contains('td', 'Тестовое изделие').should('not.exist');
    cy.contains('td', 'Другое изделие').should('not.exist');
  });

  it('должен показывать и скрывать панель массовых действий при выборе деталей', () => {
    cy.get('#bulk-actions-bar').should('have.class', 'translate-y-full');

    cy.contains('td', 'Тестовое изделие').click();
    
    cy.contains('a', 'CY-TEST-001').parents('tr').find('.part-checkbox').check();

    cy.get('#bulk-actions-bar').should('not.have.class', 'translate-y-full');
    cy.get('#bulk-actions-counter').should('contain.text', 'Выбрано: 1');

    cy.contains('a', 'CY-TEST-001').parents('tr').find('.part-checkbox').uncheck();

    cy.get('#bulk-actions-bar').should('have.class', 'translate-y-full');
    cy.get('#bulk-actions-counter').should('contain.text', 'Выбрано: 0');
  });

});