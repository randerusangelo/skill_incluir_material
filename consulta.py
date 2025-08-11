import pyodbc
from dotenv import load_dotenv
import os

load_dotenv()  # usa .env em dev

def _conn():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={os.getenv('DB_SERVER')};"
        f"DATABASE={os.getenv('DB_NAME')};"
        f"UID={os.getenv('DB_USER')};"
        f"PWD={os.getenv('DB_PASSWORD')};"
        "Trusted_Connection=no;Network=DBMSSOCN;"
    )

# ---------- CONSULTA  ----------
def buscar_localizacao(material_nome):
    try:
        conn = _conn()
        cursor = conn.cursor()
        query = """
            SELECT 
                E.nome,
                L.setor
            FROM produtos AS E
            LEFT JOIN localizacoes AS L ON E.localizacao_id = L.id
            WHERE E.nome LIKE ?
        """
        cursor.execute(query, f"%{material_nome}%")
        rows = cursor.fetchall()
        conn.close()

        if rows:
            resposta = f"Encontrei {len(rows)} iten" + ("s" if len(rows) > 1 else "") + ": "
            for row in rows:
                nome, setor = row
                resposta += f"{nome} está no setor {setor}. <break time='0.5s'/> "
            return resposta
        else:
            return "Desculpe, não encontrei esse material no sistema."
        
    except Exception as e:
        return f"Ocorreu um erro ao buscar o material: {str(e)}"

# ---------------- Inclusão de estoque ----------------
def _garantir_localizacao_por_setor(cn, setor_cod: int) -> int:
    """Retorna um localizacao_id existente para o setor; cria se não existir."""
    with cn.cursor() as cur:
        cur.execute("SELECT TOP (1) id FROM dbo.localizacoes WHERE setor = ? ORDER BY id", (setor_cod,))
        row = cur.fetchone()
        if row:
            return int(row[0])
        # cria uma localização "genérica" para o setor
        cur.execute("INSERT INTO dbo.localizacoes (setor) VALUES (?)", (setor_cod,))
        cur.execute("SELECT SCOPE_IDENTITY()")
        return int(cur.fetchone()[0])
    
def incluir_estoque(material: str, quantidade: int, setor: int,
                    user_id: str | None = None, device_id: str | None = None) -> int:
   
    if not material or not isinstance(quantidade, int) or quantidade <= 0 or setor is None:
        raise ValueError("Parâmetros inválidos (material, quantidade > 0, setor obrigatório).")

    cn = _conn()

    try:
        with cn.cursor() as cur:
            loc_id = _garantir_localizacao_por_setor(cn, setor)
            try:
                cur.execute("""
                        SELECT TOP (1) id, quantidade
                        FROM dbo.produtos
                        WHERE UPPER(nome) = UPPER(?)
                    """, (material,))
                row = cur.fetchone()
                
                if row:
                    prod_id = int(row[0])
                    cur.execute("""
                        UPDATE dbo.produtos
                        SET quantidade   = ISNULL(quantidade, 0) + ?,
                            localizacao_id = ?
                        WHERE id = ?
                    """, (quantidade, loc_id, prod_id))
                    cn.commit()
                    return prod_id
                else:
                    cur.execute("""
                        INSERT INTO dbo.produtos (nome, quantidade, preco, localizacao_id)
                        OUTPUT INSERTED.id
                        VALUES (?, ?, 0, ?)
                    """, (material, quantidade, loc_id))
                    new_id = int(cur.fetchone()[0])
                    cn.commit()
                    return new_id
            except Exception:
                cn.rollback()
                raise
    finally:
        cn.close()