import ApprovalCenterPage from "./ApprovalCenterPage";

/** “我的申请”保留独立入口，并复用审批中心的已提交申请与时间线。 */
export default function MyApplicationsPage() {
  return <ApprovalCenterPage initialTab="submitted" />;
}
