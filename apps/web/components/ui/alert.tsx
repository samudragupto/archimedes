import { cn } from "@/lib/utils";

/** shadcn-style alert: icon slot + text, default or destructive tone. */
export function Alert({
  variant = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { variant?: "default" | "destructive" }) {
  return (
    <div
      role="alert"
      className={cn(
        "relative w-full rounded-lg border p-3 text-sm",
        variant === "destructive" ? "border-red-300 bg-red-50 text-red-900" : "bg-secondary/60 text-secondary-foreground",
        "[&>svg]:absolute [&>svg]:left-3 [&>svg]:top-3.5 [&>svg~*]:pl-7",
        className,
      )}
      {...props}
    />
  );
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-sm [&_p]:leading-relaxed", className)} {...props} />;
}
