from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, send_file
import os
import tempfile
from PyPDF2 import PdfMerger
from app.models import db, AuthorizerMap, EmailLog

panel_bp = Blueprint('panel_bp', __name__)

@panel_bp.route('/')
def dashboard():
    status_filter = request.args.get('status')
    
    # Query base
    query = EmailLog.query
    if status_filter:
        query = query.filter_by(status=status_filter)
        
    logs = query.order_by(EmailLog.created_at.desc()).limit(100).all()
    
    # Contadores globales para tarjetas superiores
    total_aceptadas = EmailLog.query.filter_by(status='Aceptada').count()
    total_parciales = EmailLog.query.filter_by(status='Parcial').count()
    total_rechazadas = EmailLog.query.filter_by(status='Rechazada').count()
    
    return render_template(
        'dashboard.html', 
        logs=logs,
        total_aceptadas=total_aceptadas,
        total_parciales=total_parciales,
        total_rechazadas=total_rechazadas,
        current_filter=status_filter
    )

@panel_bp.route('/autorizadores', methods=['GET', 'POST'])
def autorizadores():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            persona = request.form.get('persona')
            autorizador = request.form.get('autorizador')
            if persona and autorizador:
                # Revisar si ya existe
                existe = AuthorizerMap.query.filter_by(persona=persona).first()
                if existe:
                    flash(f'La persona {persona} ya existe en el mapeo.', 'error')
                else:
                    nuevo_mapeo = AuthorizerMap(persona=persona, autorizador_stod=autorizador)
                    db.session.add(nuevo_mapeo)
                    db.session.commit()
                    flash('Autorizador agregado correctamente.', 'success')
                    
        elif action == 'delete':
            map_id = request.form.get('map_id')
            mapeo = AuthorizerMap.query.get(map_id)
            if mapeo:
                db.session.delete(mapeo)
                db.session.commit()
                flash('Autorizador eliminado correctamente.', 'success')
                
        elif action == 'edit':
            map_id = request.form.get('map_id')
            nueva_persona = request.form.get('persona')
            nuevo_autorizador = request.form.get('autorizador')
            mapeo = AuthorizerMap.query.get(map_id)
            if mapeo:
                mapeo.persona = nueva_persona
                mapeo.autorizador_stod = nuevo_autorizador
                db.session.commit()
                flash('Mapeo actualizado correctamente.', 'success')

        elif action == 'edit_gerente':
            old_gerente = request.form.get('old_gerente')
            new_gerente = request.form.get('new_gerente')
            if old_gerente and new_gerente:
                mapeos_a_actualizar = AuthorizerMap.query.filter_by(autorizador_stod=old_gerente).all()
                for m in mapeos_a_actualizar:
                    m.autorizador_stod = new_gerente
                db.session.commit()
                flash(f'Gerente actualizado a {new_gerente}.', 'success')

        elif action == 'delete_gerente':
            gerente = request.form.get('gerente')
            if gerente:
                AuthorizerMap.query.filter_by(autorizador_stod=gerente).delete()
                db.session.commit()
                flash(f'Gerente {gerente} y todos sus empleados fueron eliminados.', 'success')
                
        return redirect(url_for('panel_bp.autorizadores'))

    # GET request
    # GET request
    mapeos = AuthorizerMap.query.order_by(AuthorizerMap.autorizador_stod.asc(), AuthorizerMap.persona.asc()).all()
    
    # Agrupar por autorizador
    from collections import defaultdict
    mapeos_agrupados = defaultdict(list)
    for m in mapeos:
        mapeos_agrupados[m.autorizador_stod].append(m)
        
    return render_template('autorizadores.html', mapeos_agrupados=mapeos_agrupados)

@panel_bp.route('/api/archivos/<int:log_id>')
def get_archivos(log_id):
    log_entry = EmailLog.query.get_or_404(log_id)
    if not log_entry.file_path or not os.path.exists(log_entry.file_path):
        return jsonify({"exito": False, "error": "La ruta no existe o no se ha definido."})
        
    try:
        archivos = [f for f in os.listdir(log_entry.file_path) if os.path.isfile(os.path.join(log_entry.file_path, f))]
        return jsonify({"exito": True, "archivos": archivos})
    except Exception as e:
        return jsonify({"exito": False, "error": str(e)})

@panel_bp.route('/api/descargar/<int:log_id>/<path:filename>')
def descargar_archivo(log_id, filename):
    log_entry = EmailLog.query.get_or_404(log_id)
    if not log_entry.file_path or not os.path.exists(log_entry.file_path):
        return "Ruta no encontrada", 404
        
    return send_from_directory(log_entry.file_path, filename)

@panel_bp.route('/api/imprimir_docs/<int:log_id>')
def imprimir_docs(log_id):
    log_entry = EmailLog.query.get_or_404(log_id)
    if not log_entry.file_path or not os.path.exists(log_entry.file_path):
        return "Ruta no encontrada", 404
        
    try:
        merger = PdfMerger()
        archivos = [f for f in os.listdir(log_entry.file_path) if os.path.isfile(os.path.join(log_entry.file_path, f))]
        
        # Filtramos para no incluir el Comprobante_STOD
        archivos_imprimir = [f for f in archivos if "Comprobante_STOD" not in f and f.lower().endswith('.pdf')]
        
        if not archivos_imprimir:
            return "No hay documentos PDF válidos para imprimir en esta carpeta.", 404
            
        for pdf in archivos_imprimir:
            merger.append(os.path.join(log_entry.file_path, pdf))
            
        temp_dir = os.path.join(tempfile.gettempdir(), 'stod_imprimir')
        os.makedirs(temp_dir, exist_ok=True)
        salida = os.path.join(temp_dir, f'Impresion_STOD_{log_id}.pdf')
        
        merger.write(salida)
        merger.close()
        
        return send_file(salida, mimetype='application/pdf', as_attachment=False)
    except Exception as e:
        return f"Error al generar documento de impresion: {str(e)}", 500

