"""
Todoist Model Context Protocol (MCP) Server
FastMCP mimarisi ile Todoist API entegrasyonu.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from todoist_api_python.api import TodoistAPI

# .env dosyasındaki ortam değişkenlerini yükle
load_dotenv()

# MCP Sunucusunu Başlat
mcp = FastMCP("Todoist")


def _get_api_client() -> TodoistAPI:
    """TODOIST_API_TOKEN ortam değişkenini okuyarak TodoistAPI istemcisini döndürür."""
    token = os.getenv("TODOIST_API_TOKEN")
    if not token:
        raise ValueError(
            "TODOIST_API_TOKEN ortam değişkeni bulunamadı! "
            "Lütfen .env dosyanızı veya ortam değişkenlerinizi kontrol edin."
        )
    return TodoistAPI(token)


def _find_project_id(api: TodoistAPI, project_name: str) -> Optional[str]:
    """Proje adına göre eşleşen Todoist proje ID'sini bulur."""
    normalized_target = project_name.strip().lower()
    
    # Gelen Kutusu / Inbox durumları için kontrol
    inbox_aliases = ["gelen kutusu", "inbox", "gelenkutusu", "inbox/gelen kutusu"]
    is_inbox_query = normalized_target in inbox_aliases

    try:
        projects = []
        for batch in api.get_projects():
            projects.extend(batch)
    except Exception as e:
        # Projeler alınamazsa varsayılana düş
        return None

    # Eğer Inbox aranıyorsa doğrudan is_inbox_project olanı seç
    if is_inbox_query:
        for project in projects:
            if getattr(project, "is_inbox_project", False):
                return project.id
            if project.name.strip().lower() in inbox_aliases:
                return project.id
        return None

    # İsim eşleşmesi (birebir veya küçük/büyük harf duyarsız)
    for project in projects:
        if project.name.strip().lower() == normalized_target:
            return project.id

    # Kısmi eşleşme fallback
    for project in projects:
        if normalized_target in project.name.strip().lower():
            return project.id

    return None


@mcp.tool()
def create_task(
    content: str,
    description: str = "",
    project_name: str = "Gelen Kutusu",
    due_string: Optional[str] = None,
    priority: int = 1,
) -> str:
    """Todoist üzerinde yeni bir görev oluşturur.
    
    Args:
        content: Görevin başlığı / içeriği.
        description: Görevin detaylı açıklaması (opsiyonel).
        project_name: Görevin ekleneceği proje adı (varsayılan: "Gelen Kutusu").
        due_string: Doğal dil tarih/saat veya tekrarlama ifadesi (örn: "tomorrow", "every day at 14:00", "next monday").
        priority: Öncelik seviyesi (1: Normal, 2: Orta, 3: Yüksek, 4: Çok Acil).
    """
    try:
        api = _get_api_client()
        project_id = _find_project_id(api, project_name) if project_name else None

        # Priority doğrulaması (Todoist 1-4 arası kabul eder)
        clamped_priority = max(1, min(4, priority))

        task = api.add_task(
            content=content,
            description=description or None,
            project_id=project_id,
            due_string=due_string,
            priority=clamped_priority,
        )

        due_info = task.due.string if task.due and task.due.string else (due_string or "Belirtilmedi")
        project_display = project_name if project_name else "Gelen Kutusu"
        
        return (
            f"✅ Görev başarıyla oluşturuldu!\n"
            f"• ID: {task.id}\n"
            f"• Başlık: {task.content}\n"
            f"• Proje: {project_display}\n"
            f"• Öncelik: p{task.priority}\n"
            f"• Tarih / Tekrar: {due_info}\n"
            f"• URL: {task.url}"
        )
    except Exception as e:
        return f"❌ Görev oluşturulurken hata oluştu: {str(e)}"


@mcp.tool()
def list_tasks(filter_query: str = "today") -> str:
    """Todoist üzerindeki açık görevleri belirtilen filtreye göre listeler.
    
    Args:
        filter_query: Todoist filtre sorgusu (örn: "today", "tomorrow", "overdue", "p1", "all", "#ProjeAdi").
    """
    try:
        api = _get_api_client()
        tasks = []
        for batch in api.filter_tasks(query=filter_query):
            tasks.extend(batch)

        if not tasks:
            return f"ℹ️ '{filter_query}' filtresine uygun açık görev bulunamadı."

        priority_labels = {4: "🔴 p4 (Çok Acil)", 3: "🟠 p3 (Yüksek)", 2: "🔵 p2 (Orta)", 1: "⚪ p1 (Normal)"}
        
        lines = [f"📋 Açık Görevler (Filtre: '{filter_query}', Toplam: {len(tasks)}):", ""]
        for idx, task in enumerate(tasks, start=1):
            due_str = task.due.string if task.due and task.due.string else "Tarih yok"
            p_str = priority_labels.get(task.priority, f"p{task.priority}")
            lines.append(f"{idx}. [{task.id}] {task.content}")
            lines.append(f"   • Öncelik: {p_str}")
            lines.append(f"   • Tarih: {due_str}")
            if task.description:
                lines.append(f"   • Açıklama: {task.description}")
            lines.append("")

        return "\n".join(lines).strip()
    except Exception as e:
        return f"❌ Görevler listelenirken hata oluştu: {str(e)}"


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Belirtilen ID'ye sahip Todoist görevini tamamlar / kapatır.
    
    Args:
        task_id: Kapatılacak görevin Todoist ID'si.
    """
    try:
        api = _get_api_client()
        clean_task_id = str(task_id).strip()
        success = api.complete_task(task_id=clean_task_id)
        if success:
            return f"✅ Görev başarıyla tamamlandı (ID: {clean_task_id})."
        else:
            return f"⚠️ Görev tamamlanamadı veya zaten tamamlanmış olabilir (ID: {clean_task_id})."
    except Exception as e:
        return f"❌ Görev tamamlanırken hata oluştu (ID: {task_id}): {str(e)}"


if __name__ == "__main__":
    # MCP Sunucusunu stdio modunda çalıştır
    mcp.run()
