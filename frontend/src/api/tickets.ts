import { apiClient } from "./client";
import type { Department, Notification, Ticket, TicketEvent, TicketMessage, TicketPreview, TicketType, Todo, UserOption } from "../types";

export async function listTickets(): Promise<Ticket[]> { return (await apiClient.get<Ticket[]>("/tickets")).data; }
export async function previewTicket(text: string): Promise<TicketPreview> { return (await apiClient.post<TicketPreview>("/tickets/preview", { text })).data; }
export async function listParticipants(): Promise<UserOption[]> { return (await apiClient.get<UserOption[]>("/tickets/participants")).data; }
export async function listDepartments(): Promise<Department[]> { return (await apiClient.get<Department[]>("/tickets/departments")).data; }
export async function createTicket(data: { ticket_type: TicketType; subject: string; description: string; target_user_id?: string; department_id?: string; requested_department_id?: string }): Promise<Ticket> { return (await apiClient.post<Ticket>("/tickets", data)).data; }
export async function listTicketMessages(id: string): Promise<TicketMessage[]> { return (await apiClient.get<TicketMessage[]>(`/tickets/${id}/messages`)).data; }
export async function addTicketMessage(id: string, content: string): Promise<TicketMessage> { return (await apiClient.post<TicketMessage>(`/tickets/${id}/messages`, { content })).data; }
export async function ticketAction(id: string, action: string, reason = ""): Promise<Ticket> { return (await apiClient.post<Ticket>(`/tickets/${id}/${action}`, { reason })).data; }
export async function listTodos(): Promise<Todo[]> { return (await apiClient.get<Todo[]>("/todos")).data; }
export async function updateTodo(id: string, status: string): Promise<Todo> { return (await apiClient.patch<Todo>(`/todos/${id}`, { status })).data; }
export async function listAdminTickets(): Promise<Ticket[]> { return (await apiClient.get<Ticket[]>("/admin/tickets")).data; }
export async function createAdminTodo(data: { assignee_id: string; title: string; description: string; due_at?: string; ticket_id?: string }): Promise<Todo> { return (await apiClient.post<Todo>("/admin/todos", data)).data; }
export async function listAdminTodos(): Promise<Todo[]> { return (await apiClient.get<Todo[]>("/admin/todos")).data; }
export async function updateAdminTodo(id: string, status: string): Promise<Todo> { return (await apiClient.patch<Todo>(`/admin/todos/${id}`, { status })).data; }
export async function listTicketEvents(): Promise<TicketEvent[]> { return (await apiClient.get<TicketEvent[]>("/admin/ticket-events")).data; }
export async function dispatchAdminTicket(ticketId: string, assigneeId: string): Promise<Ticket> { return (await apiClient.post<Ticket>(`/admin/tickets/${ticketId}/dispatch`, { assignee_id: assigneeId })).data; }
export async function listAdminTicketMessages(id: string): Promise<TicketMessage[]> { return (await apiClient.get<TicketMessage[]>(`/tickets/${id}/messages`)).data; }
export async function listUsers(): Promise<UserOption[]> { return (await apiClient.get<UserOption[]>("/admin/users")).data; }
export async function listNotifications(): Promise<Notification[]> { return (await apiClient.get<Notification[]>("/notifications")).data; }
export async function markNotificationRead(id: string): Promise<Notification> { return (await apiClient.patch<Notification>(`/notifications/${id}/read`)).data; }
export async function markAllNotificationsRead(): Promise<void> { await apiClient.post("/notifications/read-all"); }
