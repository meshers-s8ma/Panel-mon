# app/admin/routes/report_routes.py

from flask import (Blueprint, render_template, request, jsonify, flash,
                   redirect, url_for, send_file, current_app)
from flask_login import login_required
from datetime import datetime
from sqlalchemy import func, case

from app.models.models import db, StatusHistory, Part, Permission, StatusType
from app.admin.utils import permission_required
from app.admin.forms import GenerateFromCloudForm
from app.services import graph_service, document_service

report_bp = Blueprint('report', __name__)


@report_bp.route('/')
@permission_required(Permission.VIEW_REPORTS)
def reports_index():
    """Отображает главную страницу раздела отчетов."""
    return render_template('reports/index.html')


@report_bp.route('/operator_performance')
@permission_required(Permission.VIEW_REPORTS)
def report_operator_performance():
    """Отображает страницу отчета по производительности операторов."""
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    return render_template(
        'reports/operator_performance.html',
        date_from=date_from_str,
        date_to=date_to_str
    )


@report_bp.route('/stage_duration')
@permission_required(Permission.VIEW_REPORTS)
def report_stage_duration():
    """Отображает страницу отчета по средней длительности этапов."""
    return render_template('reports/stage_duration.html')


@report_bp.route('/order_completion')
@permission_required(Permission.VIEW_REPORTS)
def report_order_completion():
    """НОВЫЙ МАРШРУТ: Отображает страницу отчета по времени выполнения заказа."""
    return render_template('reports/order_completion.html')


@report_bp.route('/defect_analysis')
@permission_required(Permission.VIEW_REPORTS)
def report_defect_analysis():
    """НОВЫЙ МАРШРУТ: Отображает страницу отчета по анализу брака."""
    return render_template('reports/defect_analysis.html')


@report_bp.route('/generate_from_cloud', methods=['GET', 'POST'])
@permission_required(Permission.VIEW_REPORTS)
def generate_from_cloud():
    """
    Отображает и обрабатывает форму для генерации Word-отчета
    из данных Excel-файла в OneDrive.
    """
    form = GenerateFromCloudForm()
    if form.validate_on_submit():
        excel_path = form.excel_path.data
        row_number = form.row_number.data
        word_template_file = form.word_template.data

        try:
            excel_bytes = graph_service.download_file_from_onedrive(excel_path)
            placeholders = graph_service.read_row_from_excel_bytes(excel_bytes, row_number)
            document_stream = document_service.generate_word_from_data(
                word_template_file.stream, placeholders
            )
            
            birka_name = placeholders.get('{{№ бирки}}', f'report_{row_number}')
            safe_filename = "".join(c for c in str(birka_name) if c.isalnum() or c in "._- ").strip()
            final_filename = f"{safe_filename}.docx"
            
            return send_file(
                document_stream,
                as_attachment=True,
                download_name=final_filename,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        except (FileNotFoundError, ValueError, IndexError, graph_service.GraphAPIError) as e:
            flash(f"Ошибка генерации отчета: {e}", "error")
        except Exception as e:
            flash(f"Произошла непредвиденная ошибка: {e}", "error")
            current_app.logger.error(f"Unhandled error in generate_from_cloud: {e}", exc_info=True)

    return render_template('reports/generate_from_cloud.html', form=form)


# --- API Эндпоинты для графиков ---

@report_bp.route('/api/reports/operator_performance')
@login_required
def api_report_operator_performance():
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    query = db.session.query(
        StatusHistory.operator_name,
        func.count(StatusHistory.id).label('stages_completed')
    ).group_by(StatusHistory.operator_name).order_by(func.count(StatusHistory.id).desc())
    if date_from_str:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        query = query.filter(StatusHistory.timestamp >= date_from)
    if date_to_str:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        query = query.filter(StatusHistory.timestamp <= date_to)
    
    data = query.all()
    
    chart_data = {
        'labels': [row.operator_name for row in data],
        'datasets': [{'label': 'Выполнено этапов', 'data': [row.stages_completed for row in data],
                      'backgroundColor': 'rgba(40, 167, 69, 0.7)', 'borderColor': 'rgba(40, 167, 69, 1)',
                      'borderWidth': 1}]
    }
    return jsonify(chart_data)


@report_bp.route('/api/reports/stage_duration')
@login_required
def api_report_stage_duration():
    engine_name = db.engine.name
    duration_expr = ((func.julianday(StatusHistory.timestamp) - func.coalesce(func.lag(func.julianday(StatusHistory.timestamp)).over(
        partition_by=StatusHistory.part_id, order_by=StatusHistory.timestamp), func.julianday(Part.date_added))) * 86400.0
    ) if engine_name == 'sqlite' else func.extract('epoch', StatusHistory.timestamp - func.coalesce(func.lag(
        StatusHistory.timestamp).over(partition_by=StatusHistory.part_id, order_by=StatusHistory.timestamp), Part.date_added))
    
    cte = db.session.query(StatusHistory.status.label('stage_name'), duration_expr.label('duration_seconds')
                          ).join(Part, Part.part_id == StatusHistory.part_id).subquery()
    
    report_data = db.session.query(cte.c.stage_name, func.avg(cte.c.duration_seconds).label('avg_duration_seconds')
                                  ).group_by(cte.c.stage_name).order_by(func.avg(cte.c.duration_seconds).desc()).all()

    chart_data = {
        'labels': [row.stage_name for row in report_data],
        'datasets': [{'label': 'Среднее время (в часах)', 'data': [(row.avg_duration_seconds / 3600) if row.avg_duration_seconds else 0 for row in report_data],
                      'backgroundColor': 'rgba(0, 123, 255, 0.7)', 'borderColor': 'rgba(0, 123, 255, 1)',
                      'borderWidth': 1}]
    }
    return jsonify(chart_data)


@report_bp.route('/api/reports/order_completion')
@login_required
def api_report_order_completion():
    """НОВЫЙ API: Возвращает данные о времени выполнения для завершенных деталей."""
    last_stage_time = db.session.query(
        StatusHistory.part_id,
        func.max(StatusHistory.timestamp).label('completion_time')
    ).group_by(StatusHistory.part_id).subquery()
    
    time_diff_expr = (func.julianday(last_stage_time.c.completion_time) - func.julianday(Part.date_added)
    ) if db.engine.name == 'sqlite' else func.extract('epoch', last_stage_time.c.completion_time - Part.date_added) / 86400.0
    
    completion_data = db.session.query(
        Part.part_id,
        time_diff_expr.label('days_taken')
    ).join(
        last_stage_time, Part.part_id == last_stage_time.c.part_id
    ).filter(
        Part.quantity_completed >= Part.quantity_total
    ).order_by(Part.date_added.desc()).limit(30).all()

    chart_data = {
        'labels': [row.part_id for row in completion_data],
        'datasets': [{'label': 'Дней на выполнение', 'data': [row.days_taken for row in completion_data],
                      'backgroundColor': 'rgba(75, 192, 192, 0.7)'}]
    }
    return jsonify(chart_data)


@report_bp.route('/api/reports/defect_analysis')
@login_required
def api_report_defect_analysis():
    """НОВЫЙ API: Возвращает данные по количеству брака на каждом этапе."""
    data = db.session.query(
        StatusHistory.status,
        func.sum(StatusHistory.quantity).label('scrapped_qty')
    ).filter(
        StatusHistory.status_type == StatusType.SCRAPPED
    ).group_by(StatusHistory.status).order_by(func.sum(StatusHistory.quantity).desc()).all()
    
    chart_data = {
        'labels': [row.status for row in data],
        'datasets': [{'label': 'Количество брака (шт.)', 'data': [row.scrapped_qty for row in data],
                      'backgroundColor': 'rgba(239, 68, 68, 0.7)', 'borderColor': 'rgba(220, 38, 38, 1)',
                      'borderWidth': 1}]
    }
    return jsonify(chart_data)