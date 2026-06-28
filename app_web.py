import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import json
from github import Github

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Calculadora Bancaria", page_icon="💳", layout="wide")

# --- SISTEMA DE SEGURIDAD Y NUBE ---
CONTRASEÑA_SECRETA = "Kira2020"
REPO_NAME = "ChristianMoscol/calculadora-intereses-bancarios"

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 Acceso Restringido")
        st.write("Por favor, ingresa la clave para usar la Calculadora Bancaria.")
        clave_ingresada = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if clave_ingresada == CONTRASEÑA_SECRETA:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        return False
    return True

if check_password():
    # --- CONEXIÓN A GITHUB API ---
    try:
        g = Github(st.secrets["GITHUB_TOKEN"])
        repo = g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"⚠️ Error conectando a GitHub. Revisa la línea 13 del código (REPO_NAME) y tu Token. Detalle: {e}")
        st.stop()

    OPCION_MANUAL = "-- Ingreso Manual --"

    # --- FUNCIONES DE BASE DE DATOS EN LA NUBE (GITHUB) ---
    def cargar_tarjetas_github():
        try:
            contents = repo.get_contents("config_tarjetas.json")
            return json.loads(contents.decoded_content.decode("utf-8"))
        except:
            return {"Scotiabank Christian": {"tea": 69.99, "cierre": 4, "pago": 1}}

    def guardar_tarjetas_github(db):
        try:
            contents = repo.get_contents("config_tarjetas.json")
            repo.update_file(contents.path, "Actualizar tarjetas desde Web", json.dumps(db, indent=4, ensure_ascii=False), contents.sha)
        except Exception:
            repo.create_file("config_tarjetas.json", "Crear config tarjetas", json.dumps(db, indent=4, ensure_ascii=False))

    # MODIFICADO: Ahora recibe la lista completa del cronograma y escribe fila por fila
    def guardar_historial_github(fecha, tarjeta, desc, monto, cuotas, diferido, cronograma):
        desc_limpia = str(desc).replace(",", " ")
        tarjeta_limpia = str(tarjeta).replace(",", " ")
        
        # Construimos el bloque de texto con todas las cuotas del cronograma
        nuevas_filas = ""
        for fila in cronograma:
            nuevas_filas += (
                f"{fecha},{tarjeta_limpia},{desc_limpia},{monto},{cuotas},{diferido},"
                f"{fila['N°']},{fila['Fecha Pago']},{fila['Días']},{fila['Saldo Inicial']},"
                f"{fila['Amortización']},{fila['Interés']},{fila['Cuota Total']},{fila['Saldo Final']}\n"
            )
        
        try:
            contents = repo.get_contents("historial_calculos.csv")
            contenido_actual = contents.decoded_content.decode("utf-8")
            nuevo_contenido = contenido_actual + nuevas_filas
            repo.update_file(contents.path, "Nuevo cronograma detallado registrado", nuevo_contenido, contents.sha)
        except Exception:
            # Cabecera extendida con datos de auditoría individuales por cuota
            cabecera = "ID_Calculo,Tarjeta,Descripcion_Compra,Monto_Total,Cuotas_Totales,Diferido_Totales,N_Cuota,Fecha_Pago,Dias,Saldo_Inicial,Amortizacion,Interes,Cuota_Total,Saldo_Final\n"
            nuevo_contenido = cabecera + nuevas_filas
            repo.create_file("historial_calculos.csv", "Crear archivo historial detallado", nuevo_contenido)

    tarjetas_db = cargar_tarjetas_github()

    # --- LÓGICA MATEMÁTICA BANCARIA ---
    def calcular_fechas_pago(fecha_compra, dia_cierre, dia_pago, cuotas, diferido):
        if fecha_compra.day <= dia_cierre:
            m, y = fecha_compra.month, fecha_compra.year
        else:
            m, y = fecha_compra.month + 1, fecha_compra.year
            if m > 12: m, y = 1, y + 1

        mes_pago_base, año_pago_base = m + 1, y
        if mes_pago_base > 12: mes_pago_base -= 12; año_pago_base += 1

        fechas_dif, fechas_real = [], []
        for d in range(diferido):
            mes, año = mes_pago_base + d, año_pago_base
            while mes > 12: mes -= 12; año += 1
            fechas_dif.append(datetime(año, mes, dia_pago))

        for c in range(cuotas):
            mes, año = mes_pago_base + diferido + c, año_pago_base
            while mes > 12: mes -= 12; año += 1
            fechas_real.append(datetime(año, mes, dia_pago))
            
        return fechas_dif, fechas_real

    def encontrar_cuota_fija(capital, tea, dias_por_periodo):
        cuota_min = capital / len(dias_por_periodo); cuota_max = capital * 2
        tolerancia = 0.0001
        while (cuota_max - cuota_min) > tolerancia:
            cuota_prueba = (cuota_min + cuota_max) / 2
            saldo = capital
            for dias in dias_por_periodo:
                interes = saldo * (((1 + tea) ** (dias / 360.0)) - 1)
                saldo -= (cuota_prueba - interes)
            if saldo > 0: cuota_min = cuota_prueba
            else: cuota_max = cuota_prueba
        return cuota_max

    def generar_pdf_bytes(df, tarjeta, desc, total_int, total_cuota):
        altura_calculada = 45 + ((len(df) + 1) * 9) + 15
        pdf = FPDF(orientation='P', unit='mm', format=(210, max(100, altura_calculada)))
        pdf.add_page()
        
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(190, 10, txt="Estado de Cuenta - Cronograma de Pagos", ln=True, align='C')
        pdf.set_font("Arial", 'I', 11)
        pdf.cell(190, 8, txt=f"Tarjeta: {tarjeta} | Detalle: {desc}", ln=True, align='C')
        pdf.ln(5)

        pdf.set_font("Arial", 'B', 10)
        encabezados = ["N°", "Fecha Pago", "Saldo Inicial", "Amortización", "Interés", "Cuota Total", "Saldo Final"]
        anchos = [14, 26, 30, 30, 30, 30, 30]
        for i, enc in enumerate(encabezados): pdf.cell(anchos[i], 10, enc, border=1, align='C')
        pdf.ln()

        pdf.set_font("Arial", '', 10)
        for _, fila in df.iterrows():
            pdf.cell(anchos[0], 9, str(fila["N°"]), border=1, align='C')
            pdf.cell(anchos[1], 9, str(fila["Fecha Pago"]), border=1, align='C')
            pdf.cell(anchos[2], 9, f"S/ {fila['Saldo Inicial']:.2f}", border=1, align='R')
            pdf.cell(anchos[3], 9, f"S/ {fila['Amortización']:.2f}", border=1, align='R')
            pdf.cell(anchos[4], 9, f"S/ {fila['Interés']:.2f}", border=1, align='R')
            pdf.cell(anchos[5], 9, f"S/ {fila['Cuota Total']:.2f}", border=1, align='R')
            pdf.cell(anchos[6], 9, f"S/ {fila['Saldo Final']:.2f}", border=1, align='R')
            pdf.ln()

        pdf.set_font("Arial", 'B', 10)
        pdf.cell(anchos[0]+anchos[1]+anchos[2]+anchos[3], 9, "TOTALES", border=1, align='R')
        pdf.cell(anchos[4], 9, f"S/ {total_int:.2f}", border=1, align='R')
        pdf.cell(anchos[5], 9, f"S/ {total_cuota:.2f}", border=1, align='R')
        pdf.cell(anchos[6], 9, "", border=1, align='R')
        
        return pdf.output(dest="S").encode("latin1")

    # --- INTERFAZ DE USUARIO (WEB) ---
    with st.sidebar:
        st.header("⚙️ Configuración")
        if st.button("🚪 Cerrar Sesión"):
            st.session_state["password_correct"] = False
            st.rerun()

        opciones_tarjetas = [OPCION_MANUAL] + list(tarjetas_db.keys())
        tarjeta_sel = st.selectbox("Seleccionar Tarjeta", opciones_tarjetas)
        
        if tarjeta_sel == OPCION_MANUAL:
            def_tea, def_cierre, def_pago = 0.0, 0, 0
            bloqueado = False
        else:
            def_tea = tarjetas_db[tarjeta_sel]["tea"]
            def_cierre = tarjetas_db[tarjeta_sel]["cierre"]
            def_pago = tarjetas_db[tarjeta_sel]["pago"]
            bloqueado = True

        with st.expander("➕ Añadir / Editar Tarjeta"):
            n_nombre = st.text_input("Nombre (Ej: BCP Kira)")
            n_tea = st.number_input("TEA (%)", min_value=0.0, format="%.2f", key="n_tea")
            n_cierre = st.number_input("Día de Cierre", min_value=1, max_value=31, step=1, key="n_cie")
            n_pago = st.number_input("Día de Pago", min_value=1, max_value=31, step=1, key="n_pag")
            
            if st.button("💾 Guardar Tarjeta"):
                if n_nombre:
                    with st.spinner('Guardando...'):
                        tarjetas_db[n_nombre] = {"tea": n_tea, "cierre": n_cierre, "pago": n_pago}
                        guardar_tarjetas_github(tarjetas_db)
                    st.success("¡Tarjeta guardada!")
                    st.rerun()
                else:
                    st.error("Ingrese un nombre.")

    with st.form("calc_form"):
        st.subheader("Datos de la Compra")
        c1, c2, c3 = st.columns(3)
        desc = c1.text_input("Descripción", placeholder="Ej: Laptop Ripley")
        monto = c2.number_input("Monto Total (S/)", min_value=0.0, value=0.0, step=10.0)
        fecha_compra = c3.date_input("Fecha de Compra")

        c4, c5, c6 = st.columns(3)
        tea = c4.number_input("TEA (%)", value=def_tea, disabled=bloqueado, format="%.2f")
        cuotas = c5.number_input("N° de Cuotas", min_value=0, value=0, step=1)
        diferido = c6.number_input("Meses Diferidos", min_value=0, value=0, step=1)

        c7, c8, _ = st.columns(3)
        dia_cierre = c7.number_input("Día de Cierre", min_value=0, max_value=31, value=def_cierre, disabled=bloqueado)
        dia_pago = c8.number_input("Día de Pago", min_value=0, max_value=31, value=def_pago, disabled=bloqueado)

        btn_calcular = st.form_submit_button("📊 Generar Cronograma", type="primary", use_container_width=True)

    if btn_calcular:
        if monto <= 0 or cuotas <= 0 or tea < 0 or dia_cierre <= 0 or dia_pago <= 0:
            st.error("⚠️ Por favor ingresa datos mayores a 0 (Monto, Cuotas, Día Cierre/Pago).")
        else:
            fechas_dif, fechas_real = calcular_fechas_pago(datetime.combine(fecha_compra, datetime.min.time()), dia_cierre, dia_pago, cuotas, diferido)
            tea_dec = tea / 100.0
            cronograma = []
            saldo = round(monto, 2)
            total_interes = 0.0
            total_cuotas = 0.0
            fecha_ant = datetime.combine(fecha_compra, datetime.min.time())
            es_primero = True

            for idx, fp in enumerate(fechas_dif):
                d = (fp - fecha_ant).days
                if es_primero: d += 1; es_primero = False
                i = round(saldo * (((1 + tea_dec) ** (d / 360.0)) - 1), 2)
                cronograma.append({
                    "N°": f"Dif {idx+1}", "Fecha Pago": fp.strftime('%Y-%m-%d'), "Días": d,
                    "Saldo Inicial": saldo, "Amortización": 0.0, "Interés": i, "Cuota Total": i, "Saldo Final": saldo
                })
                total_interes += i
                total_cuotas += i
                fecha_ant = fp

            d_reales = []
            temp_ant = fecha_ant
            for fp in fechas_real:
                d = (fp - temp_ant).days
                if es_primero: d += 1; es_primero = False
                d_reales.append(d)
                temp_ant = fp
                
            cuota_fija = round(encontrar_cuota_fija(saldo, tea_dec, d_reales), 2)
            
            for i in range(cuotas):
                d = d_reales[i]
                int_real = round(saldo * (((1 + tea_dec) ** (d / 360.0)) - 1), 2)
                if i == cuotas - 1:
                    ct = round(saldo + int_real, 2); am = saldo; sf = 0.0
                else:
                    ct = cuota_fija; am = round(ct - int_real, 2); sf = round(saldo - am, 2)

                cronograma.append({
                    "N°": str(i + 1), "Fecha Pago": fechas_real[i].strftime('%Y-%m-%d'), "Días": d,
                    "Saldo Inicial": saldo, "Amortización": am, "Interés": int_real, "Cuota Total": ct, "Saldo Final": abs(sf)
                })
                total_interes += int_real
                total_cuotas += ct
                saldo = sf

            df = pd.DataFrame(cronograma)
            
            # --- GUARDADO EN GITHUB EN SEGUNDO PLANO ---
            with st.spinner("Sincronizando cálculo detallado..."):
                # --- CORRECCIÓN DE HUSO HORARIO (PERÚ - LIMA) ---
                try:
                    from zoneinfo import ZoneInfo
                    zona_peru = ZoneInfo("America/Lima")
                    fecha_hora_peru = datetime.now(zona_peru)
                except Exception:
                    # Alternativa en caso de entornos antiguos (Restar 5 horas manualmente de UTC)
                    from datetime import timedelta, timezone
                    zona_peru = timezone(timedelta(hours=-5))
                    fecha_hora_peru = datetime.now(zona_peru)
                
                fecha_hora = fecha_hora_peru.strftime('%Y-%m-%d %H:%M:%S')
                
                # Enviamos el cronograma completo para que se desglose fila por fila con la hora de Perú
                guardar_historial_github(fecha_hora, tarjeta_sel, desc, monto, cuotas, diferido, cronograma)
            
            st.success("✅ ¡Cálculo completado!")
            st.divider()
            
            st.subheader("📋 Cronograma de Pagos")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de la Compra", f"S/ {monto:.2f}")
            col2.metric("Total Intereses", f"S/ {total_interes:.2f}")
            col3.metric("Monto Total a Pagar", f"S/ {total_cuotas:.2f}")

            st.dataframe(df, use_container_width=True, hide_index=True)

            c_down1, c_down2 = st.columns(2)
            csv = df.to_csv(index=False).encode('utf-8')
            c_down1.download_button("📥 Descargar en Excel (CSV)", data=csv, file_name=f"Cronograma_{desc}.csv", mime="text/csv", use_container_width=True)
            pdf_bytes = generar_pdf_bytes(df, tarjeta_sel, desc, total_interes, total_cuotas)
            c_down2.download_button("🖨️ Descargar PDF", data=pdf_bytes, file_name=f"Cronograma_{desc}.pdf", mime="application/pdf", use_container_width=True)
