import re


# Template dictionary in HTML format
TEMPLATES = {
    "phishing_login": {
        "subject": "Urgente: Actualización de seguridad",
        "body": """
            <html>
            <body>
                <h2>Urgente: Actualización de seguridad de cuenta requerida</h2>
                <p>Estimado/a {name},</p>
                <p>Hemos detectado actividad inusual en su cuenta. Por favor, inicie sesión inmediatamente para verificar su identidad y asegurar su cuenta:</p>
                <p><a href="{fake_login_link}">Verificar cuenta</a></p>
                <p>Si no toma acción dentro de 24 horas, su cuenta puede ser suspendida.</p>
                <p>Atentamente,<br>Equipo de Seguridad</p>
            </body>
            </html>
        """,
    },
    "new_corporate_email": {
        "subject": "Internal Mail",
        "body": """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Correo Corporativo</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 0;
                        background-color: #f4f4f4;
                    }
                    .container {
                        width: 100%;
                        max-width: 600px;
                        margin: auto;
                        background-color: #fcfffd;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    }
                    .header {
                        background-color: #023e3c;
                        padding: 0px;
                        text-align: center;
                    }
                    .header img {
                        max-width: 150px;
                    }
                    .content {
                        padding: 20px;
                        color: #333;
                    }
                    .footer {
                        background-color: #010e0c;
                        padding: 10px;
                        text-align: center;
                        color: white;
                        font-size: 10px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    .footer img {
                        max-width: 80px;
                        height: auto;
                    }
                    .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                    .quiz p {
                        font-weight: bold;
                    }
                    .quiz label {
                        display: block;
                        margin: 5px 0;
                    }
                    .signature {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }
                    @media screen and (max-width: 600px) {
                        .container {
                            width: 100%;
                        }
                        .footer {
                            flex-direction: column;
                            text-align: center;
                        }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="cid:cobra_corp_brand.png" alt="Logo de la Empresa">
                    </div>
                    <div class="content">
                        <p>Estimado/a {recipient_name},</p>
                        <p>{message_body}</p>
                    </div>
                    <div class="footer">
                        <div class="signature">
                            <img src="cid:cobra_corp_logo.png" alt="Firma Logo">
                            <div>
                                <p><strong>{sender_name}</strong></p>
                                <p>{sender_role}</p>
                                <p>{sender_email}</p>
                            </div>
                        </div>
                        <p>&copy; 2025 Cobra Corp . Todos los derechos reservados.</p>
                    </div>
                    <div class="quiz">
                        <p>¿Cómo clasificarías este correo?</p>
                        <form>
                            <label><input type="radio" name="classification" value="phishing"> a) Es phishing</label>
                            <label><input type="radio" name="classification" value="spear_phishing"> b) Es spear phishing</label>
                            <label><input type="radio" name="classification" value="error"> c) Mail enviado por error</label>
                            <label><input type="radio" name="classification" value="legitimo"> d) Mail legítimo</label>
                        </form>
                    </div>
                </div>
            </body>
            </html>
        """
    },
    "mail_2":{
        "subject": "Te quiero",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Felicitación de San Valentín</title>
            <style>
                /* Estilos generales */
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                }
                h1, h2 {
                    text-align: center;
                    color: #ff4d6d;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                    margin: 15px 0;
                }
                .heart-icon {
                    font-size: 40px;
                    color: #ff4d6d;
                    text-align: center;
                }
                .button {
                    display: block;
                    width: 200px;
                    margin: 20px auto;
                    padding: 10px;
                    background-color: #ff4d6d;
                    color: #fff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #ff1f4e;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <h1>¡Feliz Día de San Valentín!</h1>
                <div class="heart-icon">❤️</div>
                <h2>Un día lleno de amor y felicidad</h2>
                <p>En este día tan especial, quiero desearte todo lo mejor. Que el amor y la felicidad te acompañen siempre.</p>
                <p>Gracias por ser parte de mi vida.</p>
                <a href="attachment:love-letter-for-u.txt.vbs" class="button">Haz clic aquí para más sorpresas</a>
            </div>
            <div class="quiz">
                <p>Tu jefe se está declarando ¿Debes hacer click al enlace?</p>
                <form>
                    <label><input type="radio" name="classification" value="phishing"> a) No, es phishing</label>
                    <label><input type="radio" name="classification" value="spear_phishing"> b) Podría sacar información de esa carta, ha debido equivocarse</label>
                    <label><input type="radio" name="classification" value="error"> c) Es spear phishing porque claramente va dirigido a mí</label>
                    <label><input type="radio" name="classification" value="legitimo"> d) Sabía que me quería</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_3":{
        "subject": "Tu gimnasio de confianza",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Notificación de Cuota de Gimnasio</title>
            <style>
                /* Estilos generales */
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                }
                .header {
                    text-align: center;
                    padding: 10px 0;
                }
                .header img {
                    max-width: 150px;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                h1 {
                    text-align: center;
                    color: #ff6600;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                    margin: 15px 0;
                }
                .button {
                    display: block;
                    width: 200px;
                    margin: 20px auto;
                    padding: 10px;
                    background-color: #ff6600;
                    color: #fff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #cc5200;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:gym_logo.png" alt="Logo del Gimnasio">
                </div>
                <h1>¡Tu cuota de gimnacio está por vencer!</h1>
                <p>Estimada cliente, tu cuota de gimnacio está próxima a finalizar. Queremos recordarte que puedes actualizar tu pago con un nuevo método para mayor comodidad.</p>
                <p>Simplemente, envía un Bizum a +234 600 000 006.</p>
                <a href="#" class="button">Actualizar mi cuota</a>
            </div>
            <div class="quiz">
                <p>Hay algo raro en este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="phishing"> a) Faltas de ortografía</label>
                    <label><input type="radio" name="classification" value="spear_phishing"> b) mail spoofing en el emisor</label>
                    <label><input type="radio" name="classification" value="error"> c) falta firma</label>
                    <label><input type="radio" name="classification" value="legitimo"> d) todas las anteriores</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_4":{
        "subject": "NetfUx Important Notication",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Notificación Importante - Plataforma de Streaming</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #141414;
                    color: #ffffff;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: #000000;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(255, 255, 255, 0.2);
                }
                .header {
                    text-align: center;
                    padding: 20px 0;
                }
                .header img {
                    max-width: 150px;
                }
                h1 {
                    color: #e50914;
                    text-align: center;
                }
                p {
                    font-size: 16px;
                    line-height: 1.5;
                    text-align: center;
                    color: #ffffff;
                }
                .button {
                    display: block;
                    width: 200px;
                    margin: 20px auto;
                    padding: 12px;
                    background-color: #e50914;
                    color: #ffffff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #b2070f;
                }
                .quiz {
                        padding: 20px;
                        background-color: #d8e5d9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #999;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:netfux_logo.png" alt="Plataforma de Streaming">
                </div>
                <h1>Acción Requerida en tu Cuenta</h1>
                <p>Estimada {client_mail},</p>
                <p>Hemos detectado una actividad inusual en tu cuenta. Para garantizar tu seguridad, te recomendamos revisar los detalles en el documento adjunto.</p>
                <a href="cid:documento.pdf" class="button">Ver Documento</a>
                <p>Si no reconoces esta actividad, por favor, contáctanos de inmediato.</p>
                <p>Atentamente, <br> Equipo de Soporte</p>
            </div>
            <div class="quiz">
                <p>¿Cómo clasificarías este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="phishing"> a) Es phishing</label>
                    <label><input type="radio" name="classification" value="spear_phishing"> b) Es spear phishing</label>
                    <label><input type="radio" name="classification" value="error"> c) Mail enviado por error</label>
                    <label><input type="radio" name="classification" value="legitimo"> d) Mail legítimo</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_5":{
        "subject": "Información de servicio. PayPa1",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Actualización de Información de Pago</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #e3f2fd;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                }
                .header {
                    text-align: center;
                    padding: 10px 0;
                }
                .header img {
                    max-width: 150px;
                }
                h1 {
                    color: #1565c0;
                    text-align: center;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                }
                .button {
                    display: block;
                    width: 250px;
                    margin: 20px auto;
                    padding: 12px;
                    background-color: #1e88e5;
                    color: #ffffff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #1565c0;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:paypa1_logo.png" alt="Logo del Servicio de Pago">
                </div>
                <h1>¡Actualización de Información de Pago Requerida!</h1>
                <p>Estimado/a usuario/a,</p>
                <p>Hemos detectado un acceso no autorizado a nuestros servidores. Como medida de seguridad, hemos eliminado temporalmente la información de pago de todas las cuentas.</p>
                <p>Para continuar utilizando nuestros servicios sin interrupciones, por favor actualiza tu información de pago lo antes posible.</p>
                <a href="http://secure-payment-update.com" class="button">Actualizar Información de Pago</a>
                <p>Si no realizas esta acción en las próximas 24 horas, tu cuenta podría ser suspendida.</p>
                <p>Atentamente, <br> Equipo de Seguridad Financiera</p>
                <div class="footer">
                    <p>© 2025 Servicio de Pago Seguro. Todos los derechos reservados.</p>
                    <p><a href="http://secure-payment-update.com">Más información</a></p>
                </div>
            </div>
            <div class="quiz">
                <p>¿Cómo clasificarías este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="phishing"> a) Es phishing</label>
                    <label><input type="radio" name="classification" value="spear_phishing"> b) Es spear phishing</label>
                    <label><input type="radio" name="classification" value="error"> c) Mail enviado por error</label>
                    <label><input type="radio" name="classification" value="legitimo"> d) Mail legítimo</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_6":{
        "subject": "Internal Mail",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Mensaje Urgente - Acción Requerida</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                }
                .header {
                    text-align: center;
                    padding: 10px 0;
                }
                .header img {
                    max-width: 150px;
                }
                h1 {
                    color: #d9534f;
                    text-align: center;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                }
                .button {
                    display: block;
                    width: 200px;
                    margin: 20px auto;
                    padding: 12px;
                    background-color: #d9534f;
                    color: #ffffff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #b52b27;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:cobra_corp_logo.png" alt="Logo de la Empresa">
                </div>
                <h1>¡Tu cuenta ha sido comprometida!</h1>
                <p>Estimado/a usuario/a,</p>
                <p>Hemos detectado actividad sospechosa en tu cuenta. Para evitar la suspensión de tu servicio, es necesario que verifiques tu identidad de inmediato.</p>
                <a href="http://scarletwidow-security.com" class="button">Verificar mi cuenta</a>
                <p>Si no realizas esta acción en las próximas 24 horas, tu cuenta será bloqueada.</p>
                <p>Atentamente, <br> Equipo de Seguridad</p>
                <div class="footer">
                    <p>© 2025 Cobra Corp. Todos los derechos reservados.</p>
                    <p><a href="http://scarletwidow-security.com">Más información</a></p>
                </div>
                <div class="quiz">
                <p>¿Qué famoso grupo de hackers ha podido mandar este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="anonymous"> a) Anonymus</label>
                    <label><input type="radio" name="classification" value="lazarus"> b) Lazarus</label>
                    <label><input type="radio" name="classification" value="darkside"> c) Dark Side</label>
                    <label><input type="radio" name="classification" value="scarlet"> d) Scarlet Widow</label>
                </form>
            </div>
            </div>
        </body>
        </html>
        """
    },
     "mail_7":{
        "subject": "Gimnastic, notificación de seguridad",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Advertencia de Seguridad - Gymnastic</title>
            <style>
                /* Estilos generales */
                body {
                    font-family: Arial, sans-serif;
                    background: url('cid:gym_background.jpg') no-repeat center center fixed;
                    background-size: 100% 100%;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: rgba(255, 255, 255, 0.9);
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                }
                .header {
                    text-align: center;
                    padding: 10px 0;
                }
                .header img {
                    max-width: 150px;
                }
                h1 {
                    text-align: center;
                    color: #ff0000;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                    margin: 15px 0;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:gym_logo.png" alt="Logo del Gimnasio">
                </div>
                <h1>¡Importante: Verifica la Autenticidad de Nuestros Correos!</h1>
                <p>Estimado/a cliente,</p>
                <p>Hemos detectado intentos de suplantación de identidad utilizando nuestro nombre. Queremos recordarte que todos nuestros correos oficiales provienen únicamente de <strong>info@gymnastic.es</strong>.</p>
                <p>Si recibes un correo solicitando pagos, datos personales o contraseñas desde una dirección diferente, por favor, <strong>no respondas</strong> y notifícanos de inmediato.</p>
                <p>Tu seguridad es nuestra prioridad.</p>
                <p>Atentamente, <br> Equipo de Gymnastic</p>
            </div>
            <div class="quiz">
                <p>Hay algo raro en este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="false"> a) Parece falso Rick</label>
                    <label><input type="radio" name="classification" value="spear_phishingtru"> b) No es falso</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_8":{
        "subject": "Aviso, problemas con tu cuota",
        "body": """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Notificación Urgente de Cuota de Gimnasio</title>
            <style>
                /* Estilos generales */
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    margin: 0;
                    padding: 0;
                }
                .email-container {
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    padding: 20px;
                }
                .header {
                    text-align: center;
                    padding: 10px 0;
                }
                .header img {
                    max-width: 150px;
                }
                h1 {
                    text-align: center;
                    color: #ff6600;
                }
                p {
                    font-size: 16px;
                    color: #333;
                    text-align: center;
                    margin: 15px 0;
                }
                .button {
                    display: block;
                    width: 200px;
                    margin: 20px auto;
                    padding: 10px;
                    background-color: #ff6600;
                    color: #fff;
                    text-align: center;
                    font-size: 16px;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .button:hover {
                    background-color: #cc5200;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }

                .footer {
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="cid:gym_logo.png" alt="Logo del Gimnasio">
                </div>
                <h1>¡Atención: Problema con tu cuota!</h1>
                <p>Estimada cliente, hemos detectado un problema con tu pago de la cuota de gimnacio. Para evitar la suspensión de tu membresía, es necesario que verifiques tu información de pago lo antes posible.</p>
                <p>Puedes regularizar la situación enviando un Bizum a nuestro número autorizado +234 600 000 006 o accediendo a tu cuenta a través del siguiente enlace seguro.</p>
                <a href="https://gym-cobros.com/actualizacion" class="button">Actualizar mi información</a>
                <p>Si ya realizaste el pago, por favor ignora este mensaje.</p>
            </div>
            <div class="quiz">
                <p>Hay algo raro en este correo?</p>
                <form>
                    <label><input type="radio" name="classification" value="fake"> a) Es falso</label>
                    <label><input type="radio" name="classification" value="real"> b) No es falso</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_9":{
        "subject": "Internal Mail",
        "body": """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Correo Corporativo</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 0;
                        background-color: #f4f4f4;
                    }
                    .container {
                        width: 100%;
                        max-width: 600px;
                        margin: auto;
                        background-color: #fcfffd;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    }
                    .header {
                        background-color: #023e3c;
                        padding: 0px;
                        text-align: center;
                    }
                    .header img {
                        max-width: 150px;
                    }
                    .content {
                        padding: 20px;
                        color: #333;
                    }
                    .footer {
                        background-color: #010e0c;
                        padding: 10px;
                        text-align: center;
                        color: white;
                        font-size: 10px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    .footer img {
                        max-width: 80px;
                        height: auto;
                    }
                    .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                    .quiz p {
                        font-weight: bold;
                    }
                    .quiz label {
                        display: block;
                        margin: 5px 0;
                    }
                    .signature {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }
                    @media screen and (max-width: 600px) {
                        .container {
                            width: 100%;
                        }
                        .footer {
                            flex-direction: column;
                            text-align: center;
                        }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <img src="cid:cobra_corp_brand.png" alt="Logo de la Empresa">
                    </div>
                    <div class="content">
                        <p>Estimada {recipient_name},</p>
                        <p>Como sabrás, nuestro CEO Querubín Copista está cerrando una alianza estratégica en República Dominicana.</p>
                        <p>Nos ha pedido que, de forma extraordinaria, realicemos una transferencia a modo de señal con nuestros futuros socios,
                        este movimiento nos posicionará en una situación estratégica dominante frente a la competencia en el mercado LATAM.</p>
                        <p>Ten en cuenta que la información que te facilito es confidencial y debe tratarse con la máxima discreción.</p>
                        <p>Querubín necesitaría que realicemos una transferencia de 20k€ desde la cuenta que ya sabes ;) ;).</p> 
                        <p>Por favor, realiza inmediatamente la transferencia al IBAN que te facilito:</p>
                        <p>DO04ZXQU94771999332359665247</p>
                        <p>Asunto: "Colmado" (ellos se entienden)</p>
                    </div>
                    <div class="footer">
                        <div class="signature">
                            <img src="cid:cobra_corp_logo.png" alt="Firma Logo">
                            <div>
                                <p><strong>{sender_name}</strong></p>
                                <p>{sender_role}</p>
                                <p>{sender_email}</p>
                            </div>
                        </div>
                        <p>&copy; 2025 Cobra Corp . Todos los derechos reservados.</p>
                    </div>
                    <div class="quiz">
                        <p>¿Qué tipo de técnica es el conocido truco del CEO?</p>
                        <form>
                            <label><input type="radio" name="classification" value="phishing"> a) Es un correo legítimo</label>
                            <label><input type="radio" name="classification" value="whaling"> b) Es un ejemplo de whaling</label>
                            <label><input type="radio" name="classification" value="smishing"> c) Es un ejemplo de smishing</label>
                            <label><input type="radio" name="classification" value="pharming"> d) Es un ejemplo de pharming</label>
                        </form>
                    </div>
                </div>
            </body>
            </html>
        """
    },
     "mail_10":{
        "subject": "Tía muy fuerte!!",
        "body": """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Correo desde Móvil</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }
                .email-container {
                    max-width: 400px;
                    background: #ffffff;
                    padding: 15px;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    margin: auto;
                }
                .header {
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 10px;
                }
                .message {
                    font-size: 16px;
                    color: #333;
                    line-height: 1.5;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .footer {
                    font-size: 12px;
                    color: #888;
                    margin-top: 15px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    Clara_S89
                </div>
                <div class="message">
                    Hola,<br><br>
                    Acabo de salir del club de lectura y a que no sabes con quien me he cruzado, ¿Adivina?.<br><br>
                    Por cierto, no se si te ha llegado, pero parece que han cambiado el método de pago del gym, <br>
                    te hago copy paste del link que me llegó por correo.<br>
                    "Puedes ver más detalles <a href="http://www.paypa1.com">aquí</a>."<br>
                    ¡Nos hablamos pronto!
                </div>
                <div class="footer">
                    Enviado desde mi dispositivo móvil
                </div>
            </div>
        </body>
        <body>
            <div class="quiz">
                <p>¿Qué técnica han utilizado para engañar a Clara?</p>
                <form>
                    <label><input type="radio" name="classification" value="link injection"> a) Usaron link injection</label>
                    <label><input type="radio" name="classification" value="whaling"> b) Es un ejemplo de whaling</label>
                    <label><input type="radio" name="classification" value="smishing"> c) Es un ejemplo de smishing</label>
                    <label><input type="radio" name="classification" value="mail spoofing"> d) Usaron mail spoofing</label>
                </form>
            </div>
        </body>
        </html>
        """
    },
     "mail_11":{
        "subject": "Porfa necesito un favor",
        "body": """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Urgente: Necesito tu ayuda, Laura</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }
                .email-container {
                    max-width: 500px;
                    background: #ffffff;
                    padding: 15px;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    margin: auto;
                }
                .email-header {
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 10px;
                }
                .email-body {
                    font-size: 16px;
                    color: #333;
                    line-height: 1.5;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .email-footer {
                    font-size: 12px;
                    color: #888;
                    margin-top: 15px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="email-header">
                    <strong>De:</strong> novio<br>
                    <strong>Para:</strong> lau_95fb<br>
                    <strong>Asunto:</strong> Urgente: Necesito tu ayuda, Laura
                </div>
                <div class="email-body">
                    Hola mi amor,<br><br>
                    Estoy en un gran apuro. Estoy de viaje y he tenido un problema con mi tarjeta, no puedo acceder a mi cuenta bancaria y necesito hacer un pago urgente para no perder la reserva del hotel. No quiero preocupar a nadie más, por eso te escribo a ti.<br><br>
                    ¿Podrías hacerme el favor de enviarme 750€ lo antes posible? Puedes hacerlo mediante esta plataforma segura: <a href="https://www.pagos-urgentes.com">Realizar Pago</a>.<br><br>
                    Prometo devolvértelo en cuanto regrese. Por favor, dime si puedes ayudarme.<br><br>
                    Te amo ❤️<br>
                    David
                </div>
                <div class="email-footer">
                    *Este mensaje ha sido enviado desde un dispositivo móvil. Respóndeme lo antes posible, por favor.
                </div>
            </div>
        </body>
        <body>
            <div class="quiz">
                <p>¿Qué procedimiento han utilizado para esta campaña?</p>
                <form>
                    <label><input type="radio" name="classification" value="link injection"> a) Usa link injection</label>
                    <label><input type="radio" name="classification" value="ingeniería social"> b) Llevaron a cabo un proceso de ingeniería social</label>
                    <label><input type="radio" name="classification" value="smishing"> c) Es un ejemplo de smishing</label>
                    <label><input type="radio" name="classification" value="mail spoofing"> d) Es un ejemplo de pharming</label>
                </form>
            </div>
        </boody>
        </html>
        """
    },
     "mail_12":{
        "subject": "Últimas oportunidades",
        "body": """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Oportunidad Única de Inversión</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    padding: 20px;
                }
                .email-container {
                    max-width: 500px;
                    background: #ffffff;
                    padding: 15px;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    margin: auto;
                }
                .email-header {
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 10px;
                }
                .email-body {
                    font-size: 16px;
                    color: #333;
                    line-height: 1.5;
                }
                .quiz {
                        padding: 20px;
                        background-color: #e8f5e9;
                        margin: 20px;
                        border-radius: 5px;
                    }
                .quiz p {
                    font-weight: bold;
                }
                .quiz label {
                    display: block;
                    margin: 5px 0;
                }
                .email-footer {
                    font-size: 12px;
                    color: #888;
                    margin-top: 15px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="email-header">
                    <strong>De:</strong> inversion@oportunidadunica.com<br>
                    <strong>Para:</strong> lau.garcia@hmail.com<br>
                    <strong>Asunto:</strong> ¡Invierte solo 5 ScamCoins y cambia tu vida!
                </div>
                <div class="email-body">
                    Estimado/a lau_95fb,<br><br>
                    No pierdas esta increíble oportunidad de multiplicar tu inversión en cuestión de días. Con solo <strong>5 ScamCoins</strong>, puedes unirte a una comunidad exclusiva de inversores que ya están generando ingresos pasivos.<br><br>
                    🚀 ¡No dejes pasar esta oportunidad! Regístrate ahora y recibe un bono exclusivo de bienvenida.<br><br>
                    <a href="https://www.inversionmilagrosa.com">Haz clic aquí para comenzar</a>.<br><br>
                    Recuerda, las plazas son limitadas y el tiempo se agota.<br><br>
                    Saludos cordiales,<br>
                    El Equipo de Oportunidad Única
                </div>
                <div class="email-footer">
                    *Este mensaje es confidencial. Si no deseas recibir más correos, haz clic en <a href="#">darse de baja</a>.
                </div>
            </div>
             <div class="quiz">
                <p>¿Es phishing?</p>
                <form>
                    <label><input type="radio" name="classification" value="no phishing"> a) Es un correo legítimo</label>
                    <label><input type="radio" name="classification" value="phishing"> b) Es phishing</label>
                </form>
            </div>
        </body>

        </html>
        """
    },
}


def replace_placeholders(template, **kwargs):
    """
    Replace placeholders in the template with provided keyword arguments.
    """
    return re.sub(
        r"\{(.*?)\}",
        lambda match: kwargs.get(match.group(1), match.group(0)),
        template,
    )


def get_template(template_name, **kwargs):
    """
    Recover and format an email template with given parameters.
    """
    template = TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"La plantilla '{template_name}' no se encontró")

    formatted_template = {}
    # print(template)
    formatted_template["subject"] = template.get("subject", "No subject")
    formatted_template["body"] = replace_placeholders(
        template.get("body", "No body"), **kwargs
    )
    return formatted_template
