"""Catalogo de la OWASP WSTG v4.2 y estado de cobertura.

Esta es la razon de ser del proyecto: Burp conoce tus peticiones, no sabe
que pruebas de la metodologia le debes todavia al cliente. Esa
contabilidad suele acabar en una hoja de calculo aparte, y aqui vive con
el trafico que la respalda.

Los identificadores y titulos salen del documento oficial
(https://wstg.owasp.org/v4.2/) y NO de memoria: un informe de cliente con
IDs inventados es peor que no tener matriz. Los titulos se dejan en
ingles a proposito, porque son los que hay que citar.

Estados posibles de una prueba:

  NO_PROBADO  nadie la ha mirado. Es el estado inicial y el que de verdad
              importa: lo que falta por hacer.
  PROBADO     hay evidencia automatica —un candidato con ese ID— pero
              nadie ha dictaminado.
  PASA        mirada y el objetivo la supera. La pone una persona.
  FALLA       hay un hallazgo confirmado con ese ID.
  NO_APLICA   no tiene sentido en este objetivo. La pone una persona, y
              el informe la cuenta aparte: no es lo mismo no aplicar que
              no haber mirado.
"""
from __future__ import annotations

from dataclasses import dataclass

NO_PROBADO = "no_probado"
PROBADO = "probado"
PASA = "pasa"
FALLA = "falla"
NO_APLICA = "no_aplica"

ESTADOS = (NO_PROBADO, PROBADO, PASA, FALLA, NO_APLICA)

# Los estados que una persona puede poner a mano, en el orden en que se
# recorren al pulsar la tecla. PROBADO y FALLA no estan: los pone la
# evidencia, no el dedo.
CICLO_MANUAL = (NO_PROBADO, PASA, NO_APLICA)


@dataclass(frozen=True, slots=True)
class Categoria:
    codigo: str
    nombre: str
    seccion: str


CATEGORIAS = (
    Categoria("INFO", "Recoleccion de informacion", "4.1"),
    Categoria("CONF", "Configuracion y despliegue", "4.2"),
    Categoria("IDNT", "Gestion de identidad", "4.3"),
    Categoria("ATHN", "Autenticacion", "4.4"),
    Categoria("ATHZ", "Autorizacion", "4.5"),
    Categoria("SESS", "Gestion de sesiones", "4.6"),
    Categoria("INPV", "Validacion de entrada", "4.7"),
    Categoria("ERRH", "Manejo de errores", "4.8"),
    Categoria("CRYP", "Criptografia debil", "4.9"),
    Categoria("BUSL", "Logica de negocio", "4.10"),
    Categoria("CLNT", "Lado cliente", "4.11"),
    Categoria("APIT", "APIs", "4.12"),
)

# (codigo de categoria, titulos en el orden oficial). El numero de cada
# prueba es su posicion: el primero de INFO es WSTG-INFO-01.
_TITULOS: dict[str, tuple[str, ...]] = {
    "INFO": (
        "Conduct Search Engine Discovery Reconnaissance for Information Leakage",
        "Fingerprint Web Server",
        "Review Webserver Metafiles for Information Leakage",
        "Enumerate Applications on Webserver",
        "Review Webpage Content for Information Leakage",
        "Identify Application Entry Points",
        "Map Execution Paths Through Application",
        "Fingerprint Web Application Framework",
        "Fingerprint Web Application",
        "Map Application Architecture",
    ),
    "CONF": (
        "Test Network Infrastructure Configuration",
        "Test Application Platform Configuration",
        "Test File Extensions Handling for Sensitive Information",
        "Review Old Backup and Unreferenced Files for Sensitive Information",
        "Enumerate Infrastructure and Application Admin Interfaces",
        "Test HTTP Methods",
        "Test HTTP Strict Transport Security",
        "Test RIA Cross Domain Policy",
        "Test File Permission",
        "Test for Subdomain Takeover",
        "Test Cloud Storage",
    ),
    "IDNT": (
        "Test Role Definitions",
        "Test User Registration Process",
        "Test Account Provisioning Process",
        "Testing for Account Enumeration and Guessable User Account",
        "Testing for Weak or Unenforced Username Policy",
    ),
    "ATHN": (
        "Testing for Credentials Transported over an Encrypted Channel",
        "Testing for Default Credentials",
        "Testing for Weak Lock Out Mechanism",
        "Testing for Bypassing Authentication Schema",
        "Testing for Vulnerable Remember Password",
        "Testing for Browser Cache Weaknesses",
        "Testing for Weak Password Policy",
        "Testing for Weak Security Question Answer",
        "Testing for Weak Password Change or Reset Functionalities",
        "Testing for Weaker Authentication in Alternative Channel",
    ),
    "ATHZ": (
        "Testing Directory Traversal File Include",
        "Testing for Bypassing Authorization Schema",
        "Testing for Privilege Escalation",
        "Testing for Insecure Direct Object References",
    ),
    "SESS": (
        "Testing for Session Management Schema",
        "Testing for Cookies Attributes",
        "Testing for Session Fixation",
        "Testing for Exposed Session Variables",
        "Testing for Cross Site Request Forgery",
        "Testing for Logout Functionality",
        "Testing Session Timeout",
        "Testing for Session Puzzling",
        "Testing for Session Hijacking",
    ),
    "INPV": (
        "Testing for Reflected Cross Site Scripting",
        "Testing for Stored Cross Site Scripting",
        "Testing for HTTP Verb Tampering",
        "Testing for HTTP Parameter Pollution",
        "Testing for SQL Injection",
        "Testing for LDAP Injection",
        "Testing for XML Injection",
        "Testing for SSI Injection",
        "Testing for XPath Injection",
        "Testing for IMAP SMTP Injection",
        "Testing for Code Injection",
        "Testing for Command Injection",
        "Testing for Format String Injection",
        "Testing for Incubated Vulnerability",
        "Testing for HTTP Splitting Smuggling",
        "Testing for HTTP Incoming Requests",
        "Testing for Host Header Injection",
        "Testing for Server-side Template Injection",
        "Testing for Server-Side Request Forgery",
    ),
    "ERRH": (
        "Testing for Improper Error Handling",
        "Testing for Stack Traces",
    ),
    "CRYP": (
        "Testing for Weak Transport Layer Security",
        "Testing for Padding Oracle",
        "Testing for Sensitive Information Sent via Unencrypted Channels",
        "Testing for Weak Encryption",
    ),
    "BUSL": (
        "Test Business Logic Data Validation",
        "Test Ability to Forge Requests",
        "Test Integrity Checks",
        "Test for Process Timing",
        "Test Number of Times a Function Can Be Used Limits",
        "Testing for the Circumvention of Work Flows",
        "Test Defenses Against Application Misuse",
        "Test Upload of Unexpected File Types",
        "Test Upload of Malicious Files",
    ),
    "CLNT": (
        "Testing for DOM-Based Cross Site Scripting",
        "Testing for JavaScript Execution",
        "Testing for HTML Injection",
        "Testing for Client-side URL Redirect",
        "Testing for CSS Injection",
        "Testing for Client-side Resource Manipulation",
        "Testing Cross Origin Resource Sharing",
        "Testing for Cross Site Flashing",
        "Testing for Clickjacking",
        "Testing WebSockets",
        "Testing Web Messaging",
        "Testing Browser Storage",
        "Testing for Cross Site Script Inclusion",
    ),
    "APIT": (
        "Testing GraphQL",
    ),
}


@dataclass(frozen=True, slots=True)
class Prueba:
    id: str
    categoria: str
    numero: int
    titulo: str

    @property
    def seccion(self) -> str:
        cat = next(c for c in CATEGORIAS if c.codigo == self.categoria)
        return f"{cat.seccion}.{self.numero}"


def _construir() -> dict[str, Prueba]:
    salida: dict[str, Prueba] = {}
    for cat in CATEGORIAS:
        for i, titulo in enumerate(_TITULOS[cat.codigo], start=1):
            ident = f"WSTG-{cat.codigo}-{i:02d}"
            salida[ident] = Prueba(id=ident, categoria=cat.codigo,
                                   numero=i, titulo=titulo)
    return salida


CATALOGO: dict[str, Prueba] = _construir()


def existe(ident: str) -> bool:
    return ident in CATALOGO


def por_categoria(codigo: str) -> list[Prueba]:
    return [p for p in CATALOGO.values() if p.categoria == codigo]
