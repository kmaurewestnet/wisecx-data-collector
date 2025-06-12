# WiseCX Data Collector

Aplicación para recolectar datos de la API de WiseCX y almacenarlos en una base de datos PostgreSQL.

## Estructura del Proyecto

```
.
├── .env                    # Configuración de variables de entorno
├── main.py                # Punto de entrada principal
├── wisecx_api.py          # Cliente de la API de WiseCX
├── database.py            # Gestión de la base de datos
├── models.py              # Modelos de SQLAlchemy
├── requirements.txt       # Dependencias del proyecto
└── wisecx_collector.log   # Archivo de registro
```

## Configuración

1. Crear archivo `.env` con las siguientes variables:

```env
# API Configuration
WISECX_API_KEY=your_api_key_here
WISECX_API_BASE_URL=https://api.wcx.cloud/core/v1

# Database Configuration
DB_TYPE=postgresql
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=wisecx_data

# Processing Configuration
BATCH_SIZE=100              # Número de registros por lote (default: 100)
MAX_RETRIES=3              # Máximo número de reintentos (default: 3)
RETRY_DELAY=5              # Delay entre reintentos en segundos (default: 5)

# Logging
LOG_LEVEL=INFO
```

## Estructura de la Base de Datos

### Tabla: contacts
```sql
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    wise_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    personal_id VARCHAR(50),
    last_update TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: surveys
```sql
CREATE TABLE surveys (
    id SERIAL PRIMARY KEY,
    wise_id VARCHAR(50) UNIQUE NOT NULL,
    guid VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: cases
```sql
CREATE TABLE cases (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(50) UNIQUE NOT NULL,
    group_id INTEGER,
    number VARCHAR(50),
    contact_id INTEGER REFERENCES contacts(wise_id),
    status VARCHAR(50),
    tags JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla: survey_responses
```sql
CREATE TABLE survey_responses (
    id SERIAL PRIMARY KEY,
    wise_id VARCHAR(50) UNIQUE NOT NULL,
    survey_id VARCHAR(50) REFERENCES surveys(wise_id),
    case_id VARCHAR(50) REFERENCES cases(case_id),
    contact_id VARCHAR(50) REFERENCES contacts(wise_id),
    responses JSONB,
    responded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Instalación

1. Instalar dependencias:
```bash
pip install -r requirements.txt
```

2. Crear la base de datos PostgreSQL:
```bash
createdb wisecx_data
```

3. Configurar las variables de entorno en el archivo `.env`

## Uso

Ejecutar la aplicación:
```bash
python main.py
```

## Funcionalidad

La aplicación realiza las siguientes operaciones:

1. **Autenticación**: Se conecta a la API de WiseCX usando la API key configurada
2. **Obtención de encuestas**: Recupera todas las encuestas disponibles
3. **Procesamiento limitado**: Para cada encuesta procesa **únicamente la primera página** de respuestas
4. **Guardado de datos**: Para cada respuesta:
   - Guarda la respuesta de la encuesta
   - Obtiene y guarda los detalles del contacto asociado
   - Obtiene y guarda los detalles del caso asociado
5. **Limpieza**: Elimina datos antiguos (más de 90 días por defecto)

### Características principales:

- **Paginación limitada**: La aplicación está configurada para procesar únicamente la primera página de respuestas por encuesta, optimizando el rendimiento y reduciendo la carga en la API
- **Manejo robusto de errores**: Implementa reintentos automáticos para llamadas fallidas a la API
- **Validación de datos**: Verifica que las respuestas contengan datos válidos antes de procesarlas
- **Gestión de sesiones**: Manejo automático de tokens JWT con renovación automática
- **Logging comprehensivo**: Registro detallado de todas las operaciones

## Configuración de Paginación

La aplicación está optimizada para procesar únicamente la primera página de datos:

- **Survey responses**: Solo se obtiene la primera página de respuestas por encuesta
- **Batch size**: Configurable mediante `BATCH_SIZE` (default: 100)
- **Beneficios**: Menor tiempo de ejecución, menor carga en la API, procesamiento más eficiente

## Registro (Logging)

La aplicación registra todas las operaciones en:
- **Consola**: Nivel INFO por defecto
- **Archivo**: `wisecx_collector.log` con rotación diaria y compresión
- **Retención**: 30 días de logs históricos

Ejemplo de logs:
```
2025-06-12 09:08:07.587 | INFO | main:process_survey_batch:85 - Processing survey 12345
2025-06-12 09:08:07.588 | INFO | main:process_survey_batch:94 - Found 25 responses for survey 12345, page 1 (limited to first page)
```

## Gestión de Errores

- **Timeouts**: Configuración de timeouts para conexiones (30s connect, 30s read)
- **Reintentos**: Estrategia de reintentos con backoff exponencial
- **Validación**: Validación de datos antes del procesamiento
- **Logging**: Registro detallado de errores para debugging

## Base de Datos

### Soporte para múltiples motores:
- **PostgreSQL**: Recomendado para producción
- **SQLite**: Disponible para desarrollo local

### Optimizaciones:
- **Índices**: En campos de búsqueda frecuente (wise_id, case_id, etc.)
- **Configuración SQLite**: WAL mode, cache optimizado para mejor rendimiento
- **Transacciones**: Manejo adecuado de transacciones para integridad de datos

## Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `WISECX_API_KEY` | API Key de WiseCX | *Requerido* |
| `WISECX_API_BASE_URL` | URL base de la API | `https://api.wcx.cloud/core/v1` |
| `DB_TYPE` | Tipo de base de datos | `sqlite` |
| `BATCH_SIZE` | Tamaño de lote para procesamiento | `100` |
| `MAX_RETRIES` | Máximo número de reintentos | `3` |
| `RETRY_DELAY` | Delay entre reintentos (segundos) | `5` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

## Notas Técnicas

- **IDs como strings**: Los IDs de WiseCX se almacenan como VARCHAR para evitar problemas de overflow
- **Fechas UTC**: Todas las fechas se almacenan en formato UTC
- **JSON responses**: Las respuestas de encuestas se almacenan como JSONB para flexibilidad
- **Relaciones FK**: Manejo adecuado de claves foráneas entre entidades
- **Validación de respuestas**: Solo se procesan respuestas que contienen datos válidos

## Desarrollo

### Requisitos:
- Python 3.9+
- PostgreSQL 12+ (o SQLite para desarrollo)
- Conexión a internet para acceso a la API de WiseCX

### Testing:
```bash
# Ejecutar con base de datos SQLite para pruebas
export DB_TYPE=sqlite
python main.py
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 